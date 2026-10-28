"""In-process security integration tests using a disposable Mongo-compatible store."""

import asyncio
import os
import unittest
from unittest.mock import AsyncMock, patch


os.environ.update({
    "ENVIRONMENT": "production",
    "MONGO_URL": "mongodb://127.0.0.1:27017",
    "DB_NAME": "kylot_integration_test",
    "JWT_SECRET": "integration-test-secret-at-least-32-characters",
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

from fastapi.testclient import TestClient
from mongomock_motor import AsyncMongoMockClient

from backend import migrate, server


def run(coro):
    return asyncio.run(coro)


class SecurityIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.mongo = AsyncMongoMockClient()
        self.db = self.mongo["kylot_integration_test"]
        server.db = self.db
        server.client = self.mongo
        self.client = TestClient(server.app)
        self.admin_a = {
            "id": "admin-a",
            "email": "admin-a@example.com",
            "name": "Admin A",
            "password_hash": server.hash_password("correct-password-a"),
            "role": "admin",
            "company_id": "company-a",
            "permissions": server.get_default_permissions("admin"),
        }
        self.user_a = {
            "id": "user-a",
            "email": "user-a@example.com",
            "name": "User A",
            "password_hash": server.hash_password("correct-password-user-a"),
            "role": "technicien",
            "company_id": "company-a",
            "permissions": server.get_default_permissions("technicien"),
        }
        self.admin_b = {
            "id": "admin-b",
            "email": "admin-b@example.com",
            "name": "Admin B",
            "password_hash": server.hash_password("correct-password-b"),
            "role": "admin",
            "company_id": "company-b",
            "permissions": server.get_default_permissions("admin"),
        }
        commercial_permissions = server.get_default_permissions("commercial")
        commercial_permissions["sales"]["delete"] = True
        self.commercial_a = {
            "id": "commercial-a", "email": "commercial-a@example.com", "name": "Commercial A",
            "password_hash": server.hash_password("correct-password-commercial-a"),
            # Custom operational role: own-scope plus explicit delete permission.
            # This exercises row-level authorization independently of the built-in
            # commercial role, whose delete permission is intentionally hard-denied.
            "role": "closer", "company_id": "company-a", "permissions": commercial_permissions,
        }
        self.commercial_other = {
            "id": "commercial-other", "email": "commercial-other@example.com", "name": "Commercial Other",
            "password_hash": server.hash_password("correct-password-commercial-other"),
            "role": "commercial", "company_id": "company-a",
            "permissions": server.get_default_permissions("commercial"),
        }
        run(self.db.users.insert_many([self.admin_a, self.user_a, self.admin_b, self.commercial_a, self.commercial_other]))
        self.headers_a = {
            "Authorization": f"Bearer {server.create_access_token(self.admin_a['id'], self.admin_a['email'])}"
        }
        self.headers_b = {
            "Authorization": f"Bearer {server.create_access_token(self.admin_b['id'], self.admin_b['email'])}"
        }
        self.headers_commercial_a = {
            "Authorization": f"Bearer {server.create_access_token(self.commercial_a['id'], self.commercial_a['email'])}"
        }

    def tearDown(self):
        self.client.close()
        self.mongo.close()

    def test_client_body_cannot_select_another_company(self):
        response = self.client.post(
            "/api/clients",
            headers=self.headers_a,
            json={"name": "Client A", "company_id": "company-b"},
        )
        self.assertEqual(response.status_code, 200, response.text)
        created = response.json()
        stored = run(self.db.clients.find_one({"id": created["id"]}))
        self.assertEqual(stored["company_id"], "company-a")
        other_tenant = self.client.get("/api/clients", headers=self.headers_b)
        self.assertNotIn(created["id"], {row["id"] for row in other_tenant.json()})

    def test_event_rejects_cross_company_participant(self):
        rejected = self.client.post(
            "/api/events",
            headers=self.headers_a,
            json={"title": "Secret A", "date": "2026-10-20", "participants": ["admin-b"]},
        )
        self.assertEqual(rejected.status_code, 400, rejected.text)
        accepted = self.client.post(
            "/api/events",
            headers=self.headers_a,
            json={"title": "Event A", "date": "2026-10-20", "participants": ["user-a", "user-a"]},
        )
        self.assertEqual(accepted.status_code, 200, accepted.text)
        self.assertEqual(accepted.json()["participants"], ["user-a"])
        events_b = self.client.get("/api/events", headers=self.headers_b)
        self.assertEqual(events_b.json(), [])

    def test_stock_holder_and_transfer_reject_cross_company_users(self):
        run(self.db.stock.insert_one({
            "id": "stock-a",
            "company_id": "company-a",
            "product_key": "cable",
            "product_name": "Cable",
            "stock_disponible": 10,
            "holders": [],
        }))
        rejected_holder = self.client.post(
            "/api/stock/stock-a/holder",
            headers=self.headers_a,
            json={"user_id": "admin-b", "name": "Forged", "quantity": 2},
        )
        self.assertEqual(rejected_holder.status_code, 400, rejected_holder.text)
        accepted_holder = self.client.post(
            "/api/stock/stock-a/holder",
            headers=self.headers_a,
            json={"user_id": "user-a", "name": "Forged", "quantity": 2},
        )
        self.assertEqual(accepted_holder.status_code, 200, accepted_holder.text)
        self.assertEqual(accepted_holder.json()["holders"][0]["name"], "User A")
        rejected_transfer = self.client.post(
            "/api/stock/stock-a/transfer",
            headers=self.headers_a,
            json={"from_user_id": None, "to_user_id": "admin-b", "quantity": 1},
        )
        self.assertEqual(rejected_transfer.status_code, 400, rejected_transfer.text)

    def test_login_lockout_is_shared_in_database_without_plain_email(self):
        payload = {"email": self.admin_a["email"], "password": "wrong-password"}
        for _ in range(server._LOGIN_MAX_ATTEMPTS):
            response = self.client.post("/api/auth/login", json=payload)
            self.assertEqual(response.status_code, 401, response.text)
        locked = self.client.post("/api/auth/login", json=payload)
        self.assertEqual(locked.status_code, 429, locked.text)
        record = run(self.db.login_attempts.find_one({}))
        self.assertNotIn(self.admin_a["email"], str(record))
        self.assertEqual(record["_id"], server._login_key(self.admin_a["email"]))

    def test_logout_revokes_the_current_token(self):
        token = server.create_access_token(self.admin_a["id"], self.admin_a["email"])
        headers = {"Authorization": f"Bearer {token}"}
        self.assertEqual(self.client.get("/api/auth/me", headers=headers).status_code, 200)
        self.assertEqual(self.client.post("/api/auth/logout", headers=headers).status_code, 200)
        self.assertEqual(self.client.get("/api/auth/me", headers=headers).status_code, 401)

    def test_direct_project_id_cannot_bypass_own_scope(self):
        run(self.db.projects.insert_one({
            "id": "project-other", "company_id": "company-a", "client_id": "client-other",
            "sale_id": "sale-other", "assigned_to": [], "status": "a_planifier", "photos": [],
        }))
        run(self.db.sales.insert_one({
            "id": "sale-other", "company_id": "company-a", "client_id": "client-other",
            "commercial_user_id": "commercial-other", "commercial": "Commercial Other",
        }))
        run(self.db.clients.insert_one({"id": "client-other", "company_id": "company-a", "name": "Other"}))
        response = self.client.get("/api/projects/project-other", headers=self.headers_commercial_a)
        self.assertEqual(response.status_code, 404, response.text)

    def test_sale_delete_cannot_bypass_own_scope(self):
        run(self.db.sales.insert_one({
            "id": "sale-other-delete", "company_id": "company-a", "client_id": "client-other",
            "commercial_user_id": "commercial-other", "commercial": "Commercial Other",
        }))
        response = self.client.delete("/api/sales/sale-other-delete", headers=self.headers_commercial_a)
        self.assertEqual(response.status_code, 404, response.text)
        self.assertIsNotNone(run(self.db.sales.find_one({"id": "sale-other-delete"})))

    def test_project_photo_rejects_active_content_scheme(self):
        run(self.db.projects.insert_one({
            "id": "project-photo", "company_id": "company-a", "client_id": "client-a",
            "sale_id": "sale-a", "assigned_to": [], "status": "a_planifier", "photos": [],
        }))
        response = self.client.put(
            "/api/projects/project-photo",
            headers=self.headers_a,
            json={"photos": ["javascript:alert(1)"]},
        )
        self.assertEqual(response.status_code, 422, response.text)


class MigrationIntegrationTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.mongo = AsyncMongoMockClient()
        self.db = self.mongo["kylot_migration_test"]
        server.db = self.db
        server.client = self.mongo

    async def asyncTearDown(self):
        self.mongo.close()

    async def test_migration_records_completion_and_does_not_repeat(self):
        reconciliation = {"updated": 0}
        with (
            patch.object(server, "seed_default_company", new=AsyncMock()),
            patch.object(server, "migrate_sales_statuses", new=AsyncMock()),
            patch.object(server, "migrate_projects_assigned_to", new=AsyncMock()),
            patch.object(server, "migrate_multi_tenant", new=AsyncMock()),
            patch.object(server, "_reconcile_sales_commercials", new=AsyncMock(return_value=reconciliation)) as reconcile,
            patch.object(server, "_reconcile_cancelled_projects", new=AsyncMock()),
        ):
            self.assertEqual(await migrate.run_migrations(), 0)
            state = await self.db.migration_runs.find_one({"_id": migrate.MIGRATION_ID})
            self.assertEqual(state["status"], "completed")
            self.assertEqual(state["reconciliation"], reconciliation)
            self.assertEqual(await migrate.run_migrations(), 0)
            reconcile.assert_awaited_once()


if __name__ == "__main__":
    unittest.main()
