"""Mandatory-MFA grace-period and enforcement tests."""

import asyncio
import os
from datetime import datetime, timedelta, timezone
import unittest

os.environ.update({
    "ENVIRONMENT": "production",
    "MONGO_URL": "mongodb://127.0.0.1:27017",
    "DB_NAME": "kylot_mfa_enforcement_test",
    "JWT_SECRET": "mfa-enforcement-test-secret-at-least-32-characters",
    "FRONTEND_URL": "https://app.example.invalid",
    "CORS_ORIGINS": "https://app.example.invalid",
    "ALLOW_PUBLIC_REGISTRATION": "false",
    "ALLOW_DEMO_DATA": "false",
    "ALLOW_TOKEN_RESPONSE": "false",
    "RUN_STARTUP_MIGRATIONS": "false",
    "EXPOSE_API_DOCS": "false",
    "COOKIE_SECURE": "true",
    "COOKIE_SAMESITE": "lax",
    "MFA_ENFORCE_ADMINS": "true",
    "MFA_GRACE_DAYS": "7",
})

from fastapi.testclient import TestClient
from mongomock_motor import AsyncMongoMockClient

from backend import server


def run(coro):
    return asyncio.run(coro)


class MandatoryMfaTests(unittest.TestCase):
    def setUp(self):
        self.mongo = AsyncMongoMockClient()
        self.db = self.mongo["kylot_mfa_enforcement_test"]
        server.db = self.db
        server.client = self.mongo
        self._old_mfa_enforce = server.MFA_ENFORCE_ADMINS
        server.MFA_ENFORCE_ADMINS = True
        self.client = TestClient(server.app, base_url="https://testserver")
        self.admin = {
            "id": "admin-mfa", "email": "admin-mfa@example.com", "name": "Admin MFA",
            "role": "admin", "company_id": "company-a",
            "permissions": server.get_default_permissions("admin"),
            "password_hash": server.hash_password("V7!mQ2#pL9$xR4@t"),
            "is_active": True,
        }
        run(self.db.users.insert_one(self.admin))
        run(self.db.clients.insert_one({"id": "client-a", "company_id": "company-a", "name": "Client A"}))

    def tearDown(self):
        server.MFA_ENFORCE_ADMINS = self._old_mfa_enforce
        self.client.close()
        self.mongo.close()

    def _login(self):
        return self.client.post("/api/auth/login", json={
            "email": "admin-mfa@example.com", "password": "V7!mQ2#pL9$xR4@t",
        })

    def test_grace_period_allows_access_and_starts_deadline(self):
        response = self._login()
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertTrue(body["mfa_setup_required"])
        self.assertFalse(body["mfa_grace_expired"])
        self.assertTrue(body["mfa_grace_until"])
        stored = run(self.db.users.find_one({"id": "admin-mfa"}))
        self.assertTrue(stored.get("mfa_grace_until"))
        self.assertEqual(self.client.get("/api/clients?limit=10").status_code, 200)

    def test_expired_grace_blocks_business_api_but_allows_mfa_setup(self):
        past = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
        run(self.db.users.update_one({"id": "admin-mfa"}, {"$set": {"mfa_grace_until": past}}))
        response = self._login()
        self.assertEqual(response.status_code, 200, response.text)
        self.assertTrue(response.json()["mfa_grace_expired"])

        blocked = self.client.get("/api/clients?limit=10")
        self.assertEqual(blocked.status_code, 403, blocked.text)
        self.assertEqual(blocked.json().get("code"), "mfa_setup_required")
        self.assertEqual(self.client.get("/api/auth/me").status_code, 200)

        setup = self.client.post("/api/auth/mfa/setup", json={"password": "V7!mQ2#pL9$xR4@t"})
        self.assertEqual(setup.status_code, 200, setup.text)
        secret = setup.json()["secret"]
        confirm = self.client.post("/api/auth/mfa/confirm", json={"code": server._totp_code(secret)})
        self.assertEqual(confirm.status_code, 200, confirm.text)
        self.assertEqual(self.client.get("/api/clients?limit=10").status_code, 200)

        disable = self.client.post("/api/auth/mfa/disable", json={
            "password": "V7!mQ2#pL9$xR4@t", "code": server._totp_code(secret),
        })
        self.assertEqual(disable.status_code, 403, disable.text)

    def test_non_admin_is_not_forced(self):
        commercial = {
            "id": "commercial-mfa", "email": "commercial-mfa@example.com", "name": "Commercial",
            "role": "commercial", "company_id": "company-a",
            "permissions": server.get_default_permissions("commercial"),
            "password_hash": server.hash_password("V7!mQ2#pL9$xR4@t"),
            "is_active": True,
        }
        run(self.db.users.insert_one(commercial))
        response = self.client.post("/api/auth/login", json={
            "email": "commercial-mfa@example.com", "password": "V7!mQ2#pL9$xR4@t",
        })
        self.assertEqual(response.status_code, 200, response.text)
        self.assertFalse(response.json()["mfa_setup_required"])
        self.assertFalse(response.json()["mfa_grace_expired"])


if __name__ == "__main__":
    unittest.main()
