"""P0 regression tests: tenant isolation and authentication boundaries.

These tests run against an in-process Mongo-compatible store. They are not a
substitute for a real MongoDB concurrency/penetration test, but they exercise
the API boundary that protects one company's records from another.
"""

import asyncio
import os
import unittest
from datetime import datetime, timedelta, timezone

os.environ.update({
    "ENVIRONMENT": "production",
    "MONGO_URL": "mongodb://127.0.0.1:27017",
    "DB_NAME": "kylot_p0_tenant_auth_test",
    "JWT_SECRET": "p0-tenant-auth-test-secret-at-least-32-characters",
    "FRONTEND_URL": "https://app.example.invalid",
    "CORS_ORIGINS": "https://app.example.invalid",
    "ALLOW_PUBLIC_REGISTRATION": "false",
    "ALLOW_DEMO_DATA": "false",
    "ALLOW_TOKEN_RESPONSE": "false",
    "RUN_STARTUP_MIGRATIONS": "false",
    "EXPOSE_API_DOCS": "false",
    "COOKIE_SECURE": "true",
    "COOKIE_SAMESITE": "lax",
})

import jwt
from fastapi.testclient import TestClient
from mongomock_motor import AsyncMongoMockClient

from backend import server


def run(coro):
    return asyncio.run(coro)


class P0TenantAndAuthTests(unittest.TestCase):
    def setUp(self):
        self.mongo = AsyncMongoMockClient()
        self.db = self.mongo["kylot_p0_tenant_auth_test"]
        server.db = self.db
        server.client = self.mongo
        self.client = TestClient(server.app)

        self.admin_a = self._user("admin-a", "admin-a@example.com", "Admin A", "admin", "company-a", "correct-a")
        self.admin_b = self._user("admin-b", "admin-b@example.com", "Admin B", "admin", "company-b", "correct-b")
        self.commercial_a = self._user("commercial-a", "commercial-a@example.com", "Commercial A", "commercial", "company-a", "correct-ca")
        self.inactive_a = self._user("inactive-a", "inactive-a@example.com", "Inactive A", "commercial", "company-a", "correct-inactive", active=False)
        run(self.db.users.insert_many([self.admin_a, self.admin_b, self.commercial_a, self.inactive_a]))
        self.headers_a = self._headers(self.admin_a)
        self.headers_b = self._headers(self.admin_b)

        run(self.db.clients.insert_many([
            {"id": "client-a", "company_id": "company-a", "name": "Client A", "city": "Lyon"},
            {"id": "client-b", "company_id": "company-b", "name": "Client B", "city": "Paris"},
        ]))
        run(self.db.sales.insert_many([
            {"id": "sale-a", "company_id": "company-a", "client_id": "client-a", "service": "A", "amount": 100, "sale_date": "2026-11-01", "status": "en_cours"},
            {"id": "sale-b", "company_id": "company-b", "client_id": "client-b", "service": "B", "amount": 900, "sale_date": "2026-11-01", "status": "en_cours"},
        ]))
        run(self.db.projects.insert_many([
            {"id": "project-a", "company_id": "company-a", "sale_id": "sale-a", "client_id": "client-a", "scheduled_date": "2026-12-01"},
            {"id": "project-b", "company_id": "company-b", "sale_id": "sale-b", "client_id": "client-b", "scheduled_date": "2026-12-02"},
        ]))
        run(self.db.challenges.insert_many([
            {"id": "challenge-a", "company_id": "company-a", "name": "Challenge A", "start_date": "2026-11-01", "end_date": "2026-12-17", "criterion": "assist", "status": "active", "participant_names": [], "rewards": []},
            {"id": "challenge-b", "company_id": "company-b", "name": "Challenge B", "start_date": "2026-11-01", "end_date": "2026-12-17", "criterion": "assist", "status": "active", "participant_names": [], "rewards": []},
        ]))
        run(self.db.audit_log.insert_many([
            {"id": "audit-a", "company_id": "company-a", "user_id": "admin-a", "action": "create", "resource": "client", "resource_id": "client-a", "at": "2026-11-01T00:00:00Z"},
            {"id": "audit-b", "company_id": "company-b", "user_id": "admin-b", "action": "create", "resource": "client", "resource_id": "client-b", "at": "2026-11-01T00:00:00Z"},
        ]))
        run(self.db.notifications.insert_many([
            {"id": "notif-a", "company_id": "company-a", "user_id": "admin-a", "title": "A", "message": "A", "is_read": False, "created_at": "2026-11-01T00:00:00Z"},
            {"id": "notif-b", "company_id": "company-b", "user_id": "admin-b", "title": "B", "message": "B", "is_read": False, "created_at": "2026-11-01T00:00:00Z"},
        ]))

    def tearDown(self):
        self.client.close()
        self.mongo.close()

    def _user(self, uid, email, name, role, company_id, password, active=True):
        return {
            "id": uid, "email": email, "name": name, "role": role, "company_id": company_id,
            "password_hash": server.hash_password(password), "is_active": active,
            "permissions": server.get_default_permissions(role),
        }

    @staticmethod
    def _headers(user):
        return {"Authorization": f"Bearer {server.create_access_token(user['id'], user['email'])}"}

    def _assert_no_company_b(self, response):
        self.assertEqual(response.status_code, 200, response.text)
        self.assertNotIn("company-b", response.text)

    # ---------- tenant isolation: reads ----------

    def test_clients_are_isolated_by_company(self):
        a = self.client.get("/api/clients?limit=100", headers=self.headers_a)
        b = self.client.get("/api/clients?limit=100", headers=self.headers_b)
        self.assertEqual({x["id"] for x in a.json()}, {"client-a"})
        self.assertEqual({x["id"] for x in b.json()}, {"client-b"})

    def test_sales_are_isolated_by_company(self):
        a = self.client.get("/api/sales?limit=100", headers=self.headers_a)
        b = self.client.get("/api/sales?limit=100", headers=self.headers_b)
        self.assertEqual({x["id"] for x in a.json()}, {"sale-a"})
        self.assertEqual({x["id"] for x in b.json()}, {"sale-b"})

    def test_projects_are_isolated_by_company(self):
        a = self.client.get("/api/projects?limit=100", headers=self.headers_a)
        b = self.client.get("/api/projects?limit=100", headers=self.headers_b)
        self.assertEqual({x["id"] for x in a.json()}, {"project-a"})
        self.assertEqual({x["id"] for x in b.json()}, {"project-b"})

    def test_users_audit_notifications_and_challenges_are_isolated(self):
        users = self.client.get("/api/users", headers=self.headers_a)
        self.assertEqual({u["id"] for u in users.json()}, {"admin-a", "commercial-a", "inactive-a"})
        audit = self.client.get("/api/audit?limit=100", headers=self.headers_a)
        self.assertEqual({x["id"] for x in audit.json()}, {"audit-a"})
        notifications = self.client.get("/api/notifications", headers=self.headers_a)
        self.assertEqual({x["id"] for x in notifications.json()["items"]}, {"notif-a"})
        challenges = self.client.get("/api/challenges", headers=self.headers_a)
        self.assertEqual({x["id"] for x in challenges.json()}, {"challenge-a"})

    # ---------- tenant isolation: writes/IDOR ----------

    def test_cannot_update_or_delete_other_company_client(self):
        update = self.client.put("/api/clients/client-b", headers=self.headers_a, json={"name": "Hacked"})
        self.assertEqual(update.status_code, 404, update.text)
        delete = self.client.delete("/api/clients/client-b", headers=self.headers_a)
        self.assertEqual(delete.status_code, 404, delete.text)
        stored = run(self.db.clients.find_one({"id": "client-b"}))
        self.assertEqual(stored["name"], "Client B")

    def test_cannot_update_or_delete_other_company_sale_or_project(self):
        sale_update = self.client.put("/api/sales/sale-b", headers=self.headers_a, json={"amount": 1})
        self.assertEqual(sale_update.status_code, 404, sale_update.text)
        project_read = self.client.get("/api/projects/project-b", headers=self.headers_a)
        self.assertEqual(project_read.status_code, 404, project_read.text)
        project_update = self.client.put("/api/projects/project-b", headers=self.headers_a, json={"status": "termine"})
        self.assertEqual(project_update.status_code, 404, project_update.text)
        project_delete = self.client.delete("/api/projects/project-b", headers=self.headers_a)
        self.assertEqual(project_delete.status_code, 404, project_delete.text)
        stored = run(self.db.projects.find_one({"id": "project-b"}))
        self.assertNotEqual(stored.get("status"), "termine")
        self.assertFalse(stored.get("cancelled", False))

    def test_cannot_mutate_other_company_user_or_challenge(self):
        user_update = self.client.put("/api/users/admin-b", headers=self.headers_a, json={"role": "commercial"})
        self.assertEqual(user_update.status_code, 404, user_update.text)
        challenge_close = self.client.post("/api/challenges/challenge-b/close", headers=self.headers_a)
        self.assertEqual(challenge_close.status_code, 404, challenge_close.text)
        challenge_archive = self.client.post("/api/challenges/challenge-b/archive", headers=self.headers_a)
        self.assertEqual(challenge_archive.status_code, 404, challenge_archive.text)

    def test_cannot_create_sale_for_another_company_client(self):
        response = self.client.post("/api/sales", headers=self.headers_a, json={
            "client_id": "client-b", "service": "Injection", "amount": 100,
            "sale_date": "2026-11-04", "status": "en_cours",
        })
        self.assertIn(response.status_code, (400, 404), response.text)
        self.assertEqual(run(self.db.sales.count_documents({"company_id": "company-b"})), 1)

    # ---------- auth boundaries ----------

    def test_login_sets_secure_httponly_cookie(self):
        response = self.client.post("/api/auth/login", json={"email": "admin-a@example.com", "password": "correct-a"})
        self.assertEqual(response.status_code, 200, response.text)
        cookie = response.headers.get("set-cookie", "")
        self.assertIn("access_token=", cookie)
        self.assertIn("HttpOnly", cookie)
        self.assertIn("Secure", cookie)
        self.assertIn("SameSite=lax", cookie)

    def test_wrong_password_and_inactive_account_are_rejected(self):
        wrong = self.client.post("/api/auth/login", json={"email": "admin-a@example.com", "password": "wrong"})
        self.assertEqual(wrong.status_code, 401, wrong.text)
        inactive = self.client.post("/api/auth/login", json={"email": "inactive-a@example.com", "password": "correct-inactive"})
        self.assertEqual(inactive.status_code, 401, inactive.text)

    def test_missing_expired_and_deleted_user_tokens_are_rejected(self):
        missing = self.client.get("/api/auth/me")
        self.assertEqual(missing.status_code, 401, missing.text)

        past = datetime.now(timezone.utc) - timedelta(minutes=1)
        expired_token = jwt.encode({
            "sub": "admin-a", "email": "admin-a@example.com", "type": "access",
            "iat": int(past.timestamp()), "exp": past,
        }, server.JWT_SECRET, algorithm=server.JWT_ALGORITHM)
        expired = self.client.get("/api/auth/me", headers={"Authorization": f"Bearer {expired_token}"})
        self.assertEqual(expired.status_code, 401, expired.text)

        deleted_token = server.create_access_token("deleted-user", "deleted@example.com")
        deleted = self.client.get("/api/auth/me", headers={"Authorization": f"Bearer {deleted_token}"})
        self.assertEqual(deleted.status_code, 401, deleted.text)

    def test_non_admin_cannot_list_users_or_audit(self):
        headers = self._headers(self.commercial_a)
        self.assertEqual(self.client.get("/api/users", headers=headers).status_code, 403)
        self.assertEqual(self.client.get("/api/audit", headers=headers).status_code, 403)

    def test_tenant_filter_cannot_be_overridden_by_query_parameter(self):
        response = self.client.get("/api/clients?company_id=company-b&limit=100", headers=self.headers_a)
        self._assert_no_company_b(response)
        self.assertEqual({x["id"] for x in response.json()}, {"client-a"})


if __name__ == "__main__":
    unittest.main()
