"""Planning / chantier edge tests."""

import asyncio
import os
import unittest

os.environ.update({
    "ENVIRONMENT": "production",
    "MONGO_URL": "mongodb://127.0.0.1:27017",
    "DB_NAME": "kylot_planning_test",
    "JWT_SECRET": "planning-test-secret-at-least-32-characters",
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


class PlanningEdgeTests(unittest.TestCase):
    def setUp(self):
        self.mongo = AsyncMongoMockClient()
        self.db = self.mongo["kylot_planning_test"]
        server.db = self.db
        server.client = self.mongo
        self.client = TestClient(server.app, base_url="https://testserver")
        self.admin = {
            "id": "admin-planning", "email": "admin-planning@example.com", "name": "Admin Planning",
            "role": "admin", "company_id": "company-a",
            "permissions": server.get_default_permissions("admin"),
            "password_hash": server.hash_password("V7!mQ2#pL9$xR4@t"),
            "is_active": True,
        }
        run(self.db.users.insert_one(self.admin))
        run(self.db.clients.insert_one({"id": "client-planning", "company_id": "company-a", "name": "Client Planning"}))
        self.headers = {"Authorization": f"Bearer {server.create_access_token(self.admin['id'], self.admin['email'])}"}

    def tearDown(self):
        self.client.close()
        self.mongo.close()

    def _create_project(self, scheduled="2026-12-15"):
        sale = self.client.post("/api/sales", headers=self.headers, json={
            "client_id": "client-planning", "service": "Chantier planning", "amount": 1000,
            "sale_date": "2026-11-04", "status": "en_cours", "source": "Assist",
            "commercial": "Admin Planning", "desired_intervention_date": scheduled,
        })
        self.assertEqual(sale.status_code, 200, sale.text)
        projects = self.client.get("/api/projects?limit=100", headers=self.headers).json()
        return next(p for p in projects if p["sale_id"] == sale.json()["id"])

    def test_multi_day_fields_are_persisted(self):
        project = self._create_project()
        updated = self.client.put(f"/api/projects/{project['id']}", headers=self.headers, json={
            "duration_days": 3,
            "extra_dates": ["2026-12-20"],
            "day_exclusions": {"2026-12-16": ["Tech A"]},
        })
        self.assertEqual(updated.status_code, 200, updated.text)
        stored = self.client.get(f"/api/projects/{project['id']}", headers=self.headers).json()
        self.assertEqual(stored["duration_days"], 3)
        self.assertEqual(stored["extra_dates"], ["2026-12-20"])
        self.assertEqual(stored["day_exclusions"], {"2026-12-16": ["Tech A"]})

    def test_planning_endpoint_exposes_scheduled_project(self):
        project = self._create_project()
        planning = self.client.get("/api/planning/projects", headers=self.headers)
        self.assertEqual(planning.status_code, 200, planning.text)
        row = next(p for p in planning.json() if p["id"] == project["id"])
        self.assertEqual(row["scheduled_date"], "2026-12-15")

    def test_invalid_duration_and_date_are_rejected(self):
        project = self._create_project()
        bad_duration = self.client.put(f"/api/projects/{project['id']}", headers=self.headers, json={"duration_days": 0})
        self.assertEqual(bad_duration.status_code, 422, bad_duration.text)
        bad_date = self.client.put(f"/api/projects/{project['id']}", headers=self.headers, json={"scheduled_date": "2026-13-01"})
        self.assertEqual(bad_date.status_code, 422, bad_date.text)

    def test_cancelled_project_is_hidden_from_default_list_but_recoverable(self):
        project = self._create_project()
        deleted = self.client.delete(f"/api/projects/{project['id']}", headers=self.headers)
        self.assertEqual(deleted.status_code, 200, deleted.text)
        visible = self.client.get("/api/projects?limit=100", headers=self.headers).json()
        self.assertNotIn(project["id"], {p["id"] for p in visible})
        only_deleted = self.client.get("/api/projects?include_deleted=only&limit=100", headers=self.headers).json()
        self.assertIn(project["id"], {p["id"] for p in only_deleted})
        restored = self.client.post(f"/api/projects/{project['id']}/restore", headers=self.headers)
        self.assertEqual(restored.status_code, 200, restored.text)
        visible_after = self.client.get("/api/projects?limit=100", headers=self.headers).json()
        self.assertIn(project["id"], {p["id"] for p in visible_after})


if __name__ == "__main__":
    unittest.main()
