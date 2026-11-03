"""Tests for admin MFA (TOTP + recovery codes).

These tests exercise the HTTP flow with a disposable Mongo-compatible store.
They do not replace an authenticator-app/browser test.
"""

import os
import unittest

os.environ.update({
    "ENVIRONMENT": "production",
    "MONGO_URL": "mongodb://127.0.0.1:27017",
    "DB_NAME": "kylot_mfa_test",
    "JWT_SECRET": "mfa-test-key-7c1b5e9a3d2f8c4b",
    "FRONTEND_URL": "https://app.example.invalid",
    "CORS_ORIGINS": "https://app.example.invalid",
    "ALLOW_PUBLIC_REGISTRATION": "false",
    "ALLOW_DEMO_DATA": "false",
    "ALLOW_TOKEN_RESPONSE": "false",
    "RUN_STARTUP_MIGRATIONS": "false",
    "EXPOSE_API_DOCS": "false",
    "COOKIE_SECURE": "true",
    "COOKIE_SAMESITE": "lax",
    "ADMIN_EMAIL": "admin@example.com",
    "ADMIN_PASSWORD": "V7!mQ2#pL9$xR4@t",
})

from fastapi.testclient import TestClient
from mongomock_motor import AsyncMongoMockClient

from backend import server


PASSWORD = "V7!mQ2#pL9$xR4@t"


class MfaTests(unittest.TestCase):
    def setUp(self):
        self.mongo = AsyncMongoMockClient()
        self.db = self.mongo["kylot_mfa_test"]
        server.db = self.db
        server.client = self.mongo
        self.client = TestClient(server.app, base_url="https://testserver")
        self.admin = {
            "id": "admin-mfa",
            "email": "admin@example.com",
            "name": "Admin MFA",
            "role": "admin",
            "company_id": "company-a",
            "permissions": server.get_default_permissions("admin"),
            "password_hash": server.hash_password(PASSWORD),
            "is_active": True,
        }
        self.commercial = {
            "id": "commercial-mfa",
            "email": "commercial@example.com",
            "name": "Commercial",
            "role": "commercial",
            "company_id": "company-a",
            "permissions": server.get_default_permissions("commercial"),
            "password_hash": server.hash_password(PASSWORD),
            "is_active": True,
        }
        self.superadmin = {
            "id": "super-mfa",
            "email": "super@example.com",
            "name": "Super MFA",
            "role": "super_admin",
            "company_id": None,
            "permissions": {},
            "password_hash": server.hash_password(PASSWORD),
            "is_active": True,
        }
        self._run(self.db.users.insert_many([self.admin, self.commercial, self.superadmin]))
        self._run(self.db.companies.insert_one({"id": "company-a", "name": "Company A"}))
        self.admin_headers = {"Authorization": f"Bearer {server.create_access_token(self.admin['id'], self.admin['email'])}"}
        self.commercial_headers = {"Authorization": f"Bearer {server.create_access_token(self.commercial['id'], self.commercial['email'])}"}
        self.super_headers = {"Authorization": f"Bearer {server.create_access_token(self.superadmin['id'], self.superadmin['email'])}"}

    def tearDown(self):
        self.client.close()
        self.mongo.close()

    @staticmethod
    def _run(coro):
        import asyncio
        return asyncio.run(coro)

    def _setup(self):
        response = self.client.post(
            "/api/auth/mfa/setup", headers=self.admin_headers, json={"password": PASSWORD}
        )
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.headers.get("cache-control"), "no-store")
        return response.json()

    def test_totp_matches_rfc6238_vector(self):
        secret = "GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ"
        self.assertEqual(server._totp_code(secret, 59), "287082")
        self.assertTrue(server._verify_totp(secret, "287082", 59))
        self.assertFalse(server._verify_totp(secret, "000000", 59))

    def test_only_admin_can_setup_mfa(self):
        response = self.client.post(
            "/api/auth/mfa/setup", headers=self.commercial_headers, json={"password": PASSWORD}
        )
        self.assertEqual(response.status_code, 403, response.text)

    def test_setup_confirm_login_and_disable(self):
        setup = self._setup()
        self.assertIn("secret", setup)
        self.assertTrue(setup["otpauth_uri"].startswith("otpauth://totp/"))
        self.assertTrue(setup["qr_code"].startswith("data:image/svg+xml;base64,"))

        bad = self.client.post(
            "/api/auth/mfa/confirm", headers=self.admin_headers, json={"code": "000000"}
        )
        self.assertEqual(bad.status_code, 400, bad.text)

        code = server._totp_code(setup["secret"])
        confirm = self.client.post(
            "/api/auth/mfa/confirm", headers=self.admin_headers, json={"code": code}
        )
        self.assertEqual(confirm.status_code, 200, confirm.text)
        recovery = confirm.json()["recovery_codes"]
        self.assertEqual(len(recovery), 10)

        login = self.client.post(
            "/api/auth/login", json={"email": self.admin["email"], "password": PASSWORD}
        )
        self.assertEqual(login.status_code, 200, login.text)
        self.assertEqual(login.headers.get("cache-control"), "no-store")
        self.assertTrue(login.json().get("mfa_required"))
        self.assertNotIn("user", login.json())
        challenge = login.json()["challenge"]

        verify = self.client.post(
            "/api/auth/mfa/verify",
            json={"challenge": challenge, "code": server._totp_code(setup["secret"])},
        )
        self.assertEqual(verify.status_code, 200, verify.text)
        self.assertTrue(verify.json()["user"]["mfa_enabled"])
        me = self.client.get("/api/auth/me")
        self.assertEqual(me.status_code, 200, me.text)

        disable = self.client.post(
            "/api/auth/mfa/disable",
            json={"password": PASSWORD, "code": server._totp_code(setup["secret"])},
        )
        self.assertEqual(disable.status_code, 200, disable.text)
        login_after = self.client.post(
            "/api/auth/login", json={"email": self.admin["email"], "password": PASSWORD}
        )
        self.assertEqual(login_after.status_code, 200, login_after.text)
        self.assertIn("user", login_after.json())

    def test_activation_revokes_older_sessions(self):
        old_token = server.create_access_token(self.admin["id"], self.admin["email"])
        setup = self._setup()
        code = server._totp_code(setup["secret"])
        confirm = self.client.post(
            "/api/auth/mfa/confirm", headers=self.admin_headers, json={"code": code}
        )
        self.assertEqual(confirm.status_code, 200, confirm.text)
        old_client = TestClient(server.app, base_url="https://testserver")
        try:
            old_me = old_client.get(
                "/api/auth/me", headers={"Authorization": f"Bearer {old_token}"}
            )
            self.assertEqual(old_me.status_code, 401, old_me.text)
        finally:
            old_client.close()
        # Le cookie renvoye par la confirmation reste valide.
        current = self.client.get("/api/auth/me")
        self.assertEqual(current.status_code, 200, current.text)

    def test_recovery_code_is_single_use(self):
        setup = self._setup()
        code = server._totp_code(setup["secret"])
        confirm = self.client.post(
            "/api/auth/mfa/confirm", headers=self.admin_headers, json={"code": code}
        )
        self.assertEqual(confirm.status_code, 200, confirm.text)
        recovery = confirm.json()["recovery_codes"][0]

        login = self.client.post(
            "/api/auth/login", json={"email": self.admin["email"], "password": PASSWORD}
        )
        challenge = login.json()["challenge"]
        first = self.client.post(
            "/api/auth/mfa/verify", json={"challenge": challenge, "code": recovery}
        )
        self.assertEqual(first.status_code, 200, first.text)
        self.assertTrue(first.json()["used_recovery_code"])

        login2 = self.client.post(
            "/api/auth/login", json={"email": self.admin["email"], "password": PASSWORD}
        )
        challenge2 = login2.json()["challenge"]
        replay = self.client.post(
            "/api/auth/mfa/verify", json={"challenge": challenge2, "code": recovery}
        )
        self.assertEqual(replay.status_code, 401, replay.text)

    def test_access_token_is_not_a_valid_mfa_challenge(self):
        access = server.create_access_token(self.admin["id"], self.admin["email"])
        response = self.client.post(
            "/api/auth/mfa/verify", json={"challenge": access, "code": "123456"}
        )
        self.assertEqual(response.status_code, 401, response.text)

    def test_superadmin_can_list_users_without_mfa_secrets_and_reset_mfa(self):
        setup = self._setup()
        code = server._totp_code(setup["secret"])
        confirm = self.client.post(
            "/api/auth/mfa/confirm", headers=self.admin_headers, json={"code": code}
        )
        self.assertEqual(confirm.status_code, 200, confirm.text)
        old_token = server.create_access_token(self.admin["id"], self.admin["email"])

        # Le client principal porte le cookie admin depuis la confirmation ;
        # un client séparé évite de mélanger cookie et Bearer super-admin.
        super_client = TestClient(server.app, base_url="https://testserver")
        try:
            listing = super_client.get(
                "/api/superadmin/companies/company-a/users", headers=self.super_headers
            )
            self.assertEqual(listing.status_code, 200, listing.text)
            rows = {row["id"]: row for row in listing.json()["users"]}
            self.assertTrue(rows["admin-mfa"]["mfa_enabled"])
            self.assertNotIn("mfa_secret", rows["admin-mfa"])

            fresh_admin_headers = {
                "Authorization": f"Bearer {server.create_access_token(self.admin['id'], self.admin['email'])}"
            }
            forbidden = super_client.post(
                "/api/superadmin/users/admin-mfa/mfa/reset",
                headers=fresh_admin_headers, json={"reason": "tentative non autorisee"},
            )
            self.assertEqual(forbidden.status_code, 403, forbidden.text)

            reset = super_client.post(
                "/api/superadmin/users/admin-mfa/mfa/reset",
                headers=self.super_headers, json={"reason": "telephone perdu et codes de secours perdus"},
            )
            self.assertEqual(reset.status_code, 200, reset.text)
        finally:
            super_client.close()
        target = self._run(self.db.users.find_one({"id": "admin-mfa"}))
        self.assertFalse(target.get("mfa_enabled"))
        self.assertNotIn("mfa_secret", target)

        old_client = TestClient(server.app, base_url="https://testserver")
        try:
            old_me = old_client.get(
                "/api/auth/me", headers={"Authorization": f"Bearer {old_token}"}
            )
            self.assertEqual(old_me.status_code, 401, old_me.text)
        finally:
            old_client.close()

    def test_mfa_secrets_are_not_exposed_in_user_list(self):
        setup = self._setup()
        code = server._totp_code(setup["secret"])
        self.client.post("/api/auth/mfa/confirm", headers=self.admin_headers, json={"code": code})
        response = self.client.get("/api/users", headers=self.admin_headers)
        self.assertEqual(response.status_code, 200, response.text)
        for user in response.json():
            self.assertNotIn("mfa_secret", user)
            self.assertNotIn("mfa_pending_secret", user)
            self.assertNotIn("mfa_recovery_codes", user)
            self.assertNotIn("password_hash", user)

    def test_confirm_without_pending_setup_is_rejected(self):
        response = self.client.post(
            "/api/auth/mfa/confirm", headers=self.admin_headers, json={"code": "123456"}
        )
        self.assertEqual(response.status_code, 400, response.text)


if __name__ == "__main__":
    unittest.main()
