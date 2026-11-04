"""Tests for prospection commission month derivation from the project date."""

import os
import unittest

os.environ.update({
    "ENVIRONMENT": "production",
    "MONGO_URL": "mongodb://127.0.0.1:27017",
    "DB_NAME": "kylot_prospection_test",
    "JWT_SECRET": "prospection-test-key-7c1b5e9a3d2f8c4b",
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


def run(coro):
    import asyncio
    return asyncio.run(coro)


class ProspectionCommissionTests(unittest.TestCase):
    def setUp(self):
        self.mongo = AsyncMongoMockClient()
        self.db = self.mongo["kylot_prospection_test"]
        server.db = self.db
        server.client = self.mongo
        self.client = TestClient(server.app, base_url="https://testserver")
        self.admin = {
            "id": "admin-prospection", "email": "admin@example.com", "name": "Admin",
            "role": "admin", "company_id": "company-a",
            "permissions": server.get_default_permissions("admin"),
            "password_hash": server.hash_password("V7!mQ2#pL9$xR4@t"),
            "is_active": True,
        }
        self.prospecteur = {
            "id": "prospecteur-a", "email": "prospecteur@example.com", "name": "Prospecteur A",
            "role": "prospecteur", "company_id": "company-a",
            "permissions": server.get_default_permissions("prospecteur"),
            "password_hash": server.hash_password("V7!mQ2#pL9$xR4@t"),
            "is_active": True,
        }
        run(self.db.users.insert_many([self.admin, self.prospecteur]))
        run(self.db.sales.insert_many([
            {"id": "sale-proj", "company_id": "company-a", "client_id": "c-1",
             "sale_date": "2026-11-03", "amount": 1000, "status": "en_cours",
             "prospecteur_id": "prospecteur-a", "prospecteur_name": "Prospecteur A",
             "prospecteur_commission": 50, "service": "Assistance", "bdc": "B1"},
            {"id": "sale-manual", "company_id": "company-a", "client_id": "c-2",
             "sale_date": "2026-11-04", "amount": 2000, "status": "en_cours",
             "prospecteur_id": "prospecteur-a", "prospecteur_name": "Prospecteur A",
             "prospecteur_commission": 100, "prospect_commission_month": "2027-01",
             "service": "Assistance", "bdc": "B2"},
            {"id": "sale-fallback", "company_id": "company-a", "client_id": "c-3",
             "sale_date": "2026-11-05", "amount": 3000, "status": "en_cours",
             "prospecteur_id": "prospecteur-a", "prospecteur_name": "Prospecteur A",
             "prospecteur_commission": 150, "service": "Assistance", "bdc": "B3"},
        ]))
        run(self.db.projects.insert_one({
            "id": "project-proj", "company_id": "company-a", "sale_id": "sale-proj",
            "client_id": "c-1", "scheduled_date": "2026-12-10",
        }))
        run(self.db.projects.insert_one({
            "id": "project-done", "company_id": "company-a", "sale_id": "sale-done",
            "client_id": "c-4", "completion": {"completed_at": "2027-03-20T10:00:00+00:00"},
        }))
        run(self.db.sales.insert_one({
            "id": "sale-done", "company_id": "company-a", "client_id": "c-4",
            "sale_date": "2026-11-06", "amount": 4000, "status": "en_cours",
            "prospecteur_id": "prospecteur-a", "prospecteur_name": "Prospecteur A",
            "prospecteur_commission": 200, "service": "Assistance", "bdc": "B4",
        }))
        self.headers = {"Authorization": f"Bearer {server.create_access_token(self.admin['id'], self.admin['email'])}"}
        self.prospecteur_headers = {"Authorization": f"Bearer {server.create_access_token(self.prospecteur['id'], self.prospecteur['email'])}"}

    def tearDown(self):
        self.client.close()
        self.mongo.close()

    def test_project_month_is_used_and_manual_override_wins(self):
        response = self.client.get("/api/prospection", headers=self.headers)
        self.assertEqual(response.status_code, 200, response.text)
        rows = {row["id"]: row for row in response.json()}
        self.assertEqual(rows["sale-proj"]["commission_month"], "2026-12")
        self.assertEqual(rows["sale-proj"]["commission_month_source"], "project")
        self.assertEqual(rows["sale-manual"]["commission_month"], "2027-01")
        self.assertEqual(rows["sale-manual"]["commission_month_source"], "manual")

    def test_sale_without_project_falls_back_to_sale_month(self):
        response = self.client.get("/api/prospection", headers=self.headers)
        rows = {row["id"]: row for row in response.json()}
        self.assertEqual(rows["sale-fallback"]["commission_month"], "2026-11")
        self.assertEqual(rows["sale-fallback"]["commission_month_source"], "sale_date")

    def test_completion_date_is_used_when_no_scheduled_date(self):
        response = self.client.get("/api/prospection", headers=self.headers)
        self.assertEqual(response.status_code, 200, response.text)
        rows = {row["id"]: row for row in response.json()}
        self.assertEqual(rows["sale-done"]["commission_month"], "2027-03")
        self.assertEqual(rows["sale-done"]["commission_month_source"], "project")

    def test_project_date_change_moves_commission_month(self):
        updated = self.client.put(
            "/api/projects/project-proj",
            headers=self.headers,
            json={"scheduled_date": "2027-04-12"},
        )
        self.assertEqual(updated.status_code, 200, updated.text)
        rows = {row["id"]: row for row in self.client.get("/api/prospection", headers=self.headers).json()}
        self.assertEqual(rows["sale-proj"]["commission_month"], "2027-04")

    def test_manual_commission_update_is_persisted(self):
        updated = self.client.put(
            "/api/prospection/sale-fallback",
            headers=self.headers,
            json={"prospect_commission_month": "2027-05", "prospecteur_commission": 225},
        )
        self.assertEqual(updated.status_code, 200, updated.text)
        rows = {row["id"]: row for row in self.client.get("/api/prospection", headers=self.headers).json()}
        self.assertEqual(rows["sale-fallback"]["commission_month"], "2027-05")
        self.assertEqual(rows["sale-fallback"]["commission_month_source"], "manual")
        self.assertEqual(rows["sale-fallback"]["prospecteur_commission"], 225)

    def test_prospecteur_cannot_edit_commission(self):
        denied = self.client.put(
            "/api/prospection/sale-fallback",
            headers=self.prospecteur_headers,
            json={"prospecteur_commission": 999},
        )
        self.assertEqual(denied.status_code, 403, denied.text)


if __name__ == "__main__":
    unittest.main()
