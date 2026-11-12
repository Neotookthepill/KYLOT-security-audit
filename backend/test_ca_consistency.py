"""Le CA du dashboard et celui de la page Ventes doivent être identiques."""

import asyncio
import os
import unittest
from datetime import date, datetime, timedelta
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
             "status": "en_cours", "sale_date": today.isoformat(), "commercial": "Admin CA",
             "service": "Test", "source": "R1", "commission_rate": 0.10},
            {"id": "sale-custom", "company_id": "company-ca", "client_id": "c", "amount": 50,
             "status": "custom_metier", "sale_date": today.isoformat(), "commercial": "Admin CA",
             "service": "Test", "source": "R1"},
            {"id": "sale-cancelled", "company_id": "company-ca", "client_id": "c", "amount": 25,
             "status": "annule", "sale_date": today.isoformat(), "commercial": "Admin CA",
             "service": "Test", "source": "R1"},
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
        report = self.client.get(
            f"/api/reports/monthly?month={self.month_start[:7]}",
            headers=self.headers,
        )
        commissions = self.client.get("/api/commissions", headers=self.headers)
        self.assertEqual(dash.status_code, 200, dash.text)
        self.assertEqual(summary.status_code, 200, summary.text)
        self.assertEqual(report.status_code, 200, report.text)
        self.assertEqual(commissions.status_code, 200, commissions.text)
        self.assertEqual(dash.json()["ca"]["total"], 100.0)
        self.assertEqual(summary.json()["total"], 100.0)
        # `count` conserve le nombre de lignes de la période ; le CA, lui, ne
        # compte que les statuts qui entrent dans le chiffre d’affaires.
        self.assertEqual(summary.json()["count"], 3)
        self.assertEqual(summary.json()["ca_count"], 1)
        self.assertEqual(report.json()["totals"]["ca_total"], 100.0)
        self.assertEqual(report.json()["totals"]["sales_count"], 3)
        self.assertEqual(report.json()["totals"]["active_count"], 1)
        self.assertEqual(report.json()["totals"]["sources"]["R1"], 1)
        self.assertEqual(report.json()["totals"]["commission_total"], 10.0)
        self.assertAlmostEqual(sum(float(r.get("commission_amount") or 0) for r in commissions.json()), 10.0, places=2)

    def test_previous_month_and_status_transition_are_consistent(self):
        today = datetime.now(ZoneInfo("Europe/Paris")).date()
        prev_last = date(today.year, today.month, 1) - timedelta(days=1)
        prev_start = date(prev_last.year, prev_last.month, 1)
        prev_end = date(prev_last.year, prev_last.month, 28)
        asyncio.run(self.db.sales.insert_one({
            "id": "sale-prev", "company_id": "company-ca", "client_id": "c", "amount": 200,
            "status": "en_cours", "sale_date": prev_start.isoformat(), "commercial": "Admin CA",
            "service": "Test", "commission_rate": 0.10,
        }))
        prev_summary = self.client.get(
            f"/api/sales/summary?from_date={prev_start.isoformat()}&to_date={prev_end.isoformat()}",
            headers=self.headers,
        )
        prev_report = self.client.get(f"/api/reports/monthly?month={prev_start.isoformat()[:7]}", headers=self.headers)
        self.assertEqual(prev_summary.json()["total"], 200.0)
        self.assertEqual(prev_report.json()["totals"]["ca_total"], 200.0)

        update = self.client.put("/api/sales/sale-known", headers=self.headers, json={"status": "annule"})
        self.assertEqual(update.status_code, 200, update.text)
        dash = self.client.get("/api/dashboard/executive?period=month", headers=self.headers)
        summary = self.client.get(
            f"/api/sales/summary?from_date={self.month_start}&to_date={self.month_end}",
            headers=self.headers,
        )
        report = self.client.get(f"/api/reports/monthly?month={self.month_start[:7]}", headers=self.headers)
        self.assertEqual(dash.json()["ca"]["total"], 0.0)
        self.assertEqual(summary.json()["total"], 0.0)
        self.assertEqual(report.json()["totals"]["ca_total"], 0.0)

        restore = self.client.put("/api/sales/sale-known", headers=self.headers, json={"status": "en_cours"})
        self.assertEqual(restore.status_code, 200, restore.text)
        dash = self.client.get("/api/dashboard/executive?period=month", headers=self.headers)
        self.assertEqual(dash.json()["ca"]["total"], 100.0)

    def test_tenant_and_corrupt_rows_do_not_break_totals(self):
        other = {
            "id": "admin-other-ca", "email": "admin-other-ca@example.com", "name": "Admin Other",
            "password_hash": server.hash_password("other-password-123"),
            "role": "admin", "company_id": "company-other",
            "permissions": server.get_default_permissions("admin"),
        }
        asyncio.run(self.db.users.insert_one(other))
        other_headers = {"Authorization": "Bearer " + server.create_access_token(other["id"], other["email"])}
        self.assertEqual(self.client.get("/api/sales/summary", headers=other_headers).json()["total"], 0.0)
        self.assertEqual(self.client.get("/api/dashboard/executive?period=month", headers=other_headers).json()["ca"]["total"], 0.0)

        asyncio.run(self.db.sales.insert_one({
            "id": "sale-corrupt", "company_id": "company-ca", "client_id": "missing",
            "amount": None, "status": "custom_corrupt", "sale_date": self.month_start,
            "commercial": "Admin CA",
        }))
        summary = self.client.get(
            f"/api/sales/summary?from_date={self.month_start}&to_date={self.month_end}",
            headers=self.headers,
        )
        dash = self.client.get("/api/dashboard/executive?period=month", headers=self.headers)
        self.assertEqual(summary.status_code, 200, summary.text)
        self.assertEqual(dash.status_code, 200, dash.text)
        self.assertEqual(summary.json()["total"], 100.0)
        self.assertEqual(dash.json()["ca"]["total"], 100.0)


if __name__ == "__main__":
    unittest.main()
