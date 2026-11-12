"""Le CA du dashboard et celui de la page Ventes doivent être identiques."""

import asyncio
import os
import unittest
from datetime import date, datetime
from zoneinfo import ZoneInfo

os.environ.update({
    "ENVIRONMENT": "production",
    "MONGO_URL": "mongodb://127.0.0.1:27017",
    "DB_NAME": "kylot_ca_consistency_test",
    "JWT_SECRET": "ca-consistency-secret-at-least-32-characters",
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


class CaConsistencyTests(unittest.TestCase):
    def setUp(self):
        self.mongo = AsyncMongoMockClient()
        self.db = self.mongo["kylot_ca_consistency_test"]
        server.db = self.db
        server.client = self.mongo
        self.client = TestClient(server.app)
        self.admin = {
            "id": "admin-ca", "email": "admin-ca@example.com", "name": "Admin CA",
            "password_hash": server.hash_password("ca-consistency-password"),
            "role": "admin", "company_id": "company-ca",
            "permissions": server.get_default_permissions("admin"),
        }
        asyncio.run(self.db.users.insert_one(self.admin))
        self.headers = {"Authorization": "Bearer " + server.create_access_token(self.admin["id"], self.admin["email"])}
        today = datetime.now(ZoneInfo("Europe/Paris")).date()
        self.month_start = date(today.year, today.month, 1).isoformat()
        self.month_end = date(today.year, today.month, 28).isoformat()
        asyncio.run(self.db.sales.insert_many([
            {"id": "sale-known", "company_id": "company-ca", "client_id": "c", "amount": 100,
             "status": "en_cours", "sale_date": today.isoformat(), "commercial": "Admin CA"},
            {"id": "sale-custom", "company_id": "company-ca", "client_id": "c", "amount": 50,
             "status": "custom_metier", "sale_date": today.isoformat(), "commercial": "Admin CA"},
            {"id": "sale-cancelled", "company_id": "company-ca", "client_id": "c", "amount": 25,
             "status": "annule", "sale_date": today.isoformat(), "commercial": "Admin CA"},
        ]))

    def tearDown(self):
        self.client.close()
        self.mongo.close()

    def test_dashboard_and_sales_summary_use_the_same_ca(self):
        dash = self.client.get("/api/dashboard/executive?period=month", headers=self.headers)
        summary = self.client.get(
            f"/api/sales/summary?from_date={self.month_start}&to_date={self.month_end}",
            headers=self.headers,
        )
        self.assertEqual(dash.status_code, 200, dash.text)
        self.assertEqual(summary.status_code, 200, summary.text)
        self.assertEqual(dash.json()["ca"]["total"], 100.0)
        self.assertEqual(summary.json()["total"], 100.0)
        self.assertEqual(summary.json()["count"], 1)


if __name__ == "__main__":
    unittest.main()
