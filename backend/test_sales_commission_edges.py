"""Advanced sales/commission regression tests (P0 business rules)."""

import asyncio
import os
import unittest

os.environ.update({
    "ENVIRONMENT": "production",
    "MONGO_URL": "mongodb://127.0.0.1:27017",
    "DB_NAME": "kylot_sales_commission_test",
    "JWT_SECRET": "sales-commission-test-secret-at-least-32-characters",
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

from backend import server


def run(coro):
    return asyncio.run(coro)


class SalesCommissionEdgeTests(unittest.TestCase):
    def setUp(self):
        self.mongo = AsyncMongoMockClient()
        self.db = self.mongo["kylot_sales_commission_test"]
        server.db = self.db
        server.client = self.mongo
        self.client = TestClient(server.app, base_url="https://testserver")
        self.admin = {
            "id": "admin-sales", "email": "admin-sales@example.com", "name": "Admin Sales",
            "role": "admin", "company_id": "company-a",
            "permissions": server.get_default_permissions("admin"),
            "password_hash": server.hash_password("V7!mQ2#pL9$xR4@t"),
            "is_active": True,
        }
        self.alice = {
            "id": "alice", "email": "alice@example.com", "name": "Alice",
            "role": "commercial", "company_id": "company-a",
            "permissions": server.get_default_permissions("commercial"),
            "password_hash": server.hash_password("V7!mQ2#pL9$xR4@t"),
            "is_active": True,
        }
        self.bob = {
            "id": "bob", "email": "bob@example.com", "name": "Bob",
            "role": "commercial", "company_id": "company-a",
            "permissions": server.get_default_permissions("commercial"),
            "password_hash": server.hash_password("V7!mQ2#pL9$xR4@t"),
            "is_active": True,
        }
        run(self.db.users.insert_many([self.admin, self.alice, self.bob]))
        run(self.db.clients.insert_one({"id": "client-a", "company_id": "company-a", "name": "Client A"}))
        self.headers = {"Authorization": f"Bearer {server.create_access_token(self.admin['id'], self.admin['email'])}"}

    def tearDown(self):
        self.client.close()
        self.mongo.close()

    def _sale(self, **overrides):
        payload = {
            "client_id": "client-a", "service": "Prestation", "amount": 1000,
            "sale_date": "2026-11-04", "status": "en_cours", "source": "R1",
            "commercial": "Alice", "commission_rate": 0.20,
        }
        payload.update(overrides)
        return self.client.post("/api/sales", headers=self.headers, json=payload)

    def test_de_sale_splits_ca_and_uses_independent_rates(self):
        created = self._sale(is_de=True, commercial_2="Bob", commission_rate_2=0.10)
        self.assertEqual(created.status_code, 200, created.text)
        sale = created.json()
        self.assertTrue(sale["is_de"])
        self.assertEqual(sale["commercial_2"], "Bob")
        self.assertEqual(sale["commission_rate_2"], 0.10)
        rows = self.client.get("/api/commissions", headers=self.headers).json()
        self.assertEqual(len(rows), 2)
        by_name = {r["commercial"]: r for r in rows}
        self.assertEqual(by_name["Alice"]["share"], 0.5)
        self.assertEqual(by_name["Bob"]["share"], 0.5)
        self.assertEqual(by_name["Alice"]["commission_amount"], 100)
        self.assertEqual(by_name["Bob"]["commission_amount"], 50)

    def test_de_sale_with_same_commercial_is_not_double_counted(self):
        created = self._sale(is_de=True, commercial_2="Alice", commission_rate_2=0.10)
        self.assertEqual(created.status_code, 200, created.text)
        rows = self.client.get("/api/commissions", headers=self.headers).json()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["commercial"], "Alice")
        self.assertEqual(rows[0]["share"], 1.0)
        self.assertEqual(rows[0]["commission_amount"], 200)

    def test_commission_month_is_preserved(self):
        created = self._sale(commission_month="2027-01", amount=1234.56, commission_rate=0.13)
        self.assertEqual(created.status_code, 200, created.text)
        rows = self.client.get("/api/commissions", headers=self.headers).json()
        self.assertEqual(rows[0]["commission_month"], "2027-01")
        self.assertEqual(rows[0]["commission_amount"], 160.49)

    def test_cancelled_and_litige_sales_are_visible_but_flagged(self):
        for status in ("annule", "litige"):
            created = self._sale(status=status, bdc=status, amount=500, commission_rate=0.1)
            self.assertEqual(created.status_code, 200, created.text)
        rows = self.client.get("/api/commissions", headers=self.headers).json()
        statuses = {r["status"] for r in rows}
        self.assertIn("annule", statuses)
        self.assertIn("litige", statuses)


if __name__ == "__main__":
    unittest.main()
