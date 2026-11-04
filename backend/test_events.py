"""Planning event visibility, location and permission tests."""

import asyncio
import os
import unittest

os.environ.update({
    "ENVIRONMENT": "production",
    "MONGO_URL": "mongodb://127.0.0.1:27017",
    "DB_NAME": "kylot_events_test",
    "JWT_SECRET": "events-test-secret-at-least-32-characters",
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


class EventTests(unittest.TestCase):
    def setUp(self):
        self.mongo = AsyncMongoMockClient()
        self.db = self.mongo["kylot_events_test"]
        server.db = self.db
        server.client = self.mongo
        self.client = TestClient(server.app, base_url="https://testserver")
        self.admin = {
            "id": "admin-events", "email": "admin-events@example.com", "name": "Admin Events",
            "role": "admin", "company_id": "company-a",
            "permissions": server.get_default_permissions("admin"),
            "password_hash": server.hash_password("V7!mQ2#pL9$xR4@t"),
            "is_active": True,
        }
        self.commercial = {
            "id": "commercial-events", "email": "commercial-events@example.com", "name": "Commercial Events",
            "role": "commercial", "company_id": "company-a",
            "permissions": server.get_default_permissions("commercial"),
            "password_hash": server.hash_password("V7!mQ2#pL9$xR4@t"),
            "is_active": True,
        }
        run(self.db.users.insert_many([self.admin, self.commercial]))
        self.admin_headers = {"Authorization": f"Bearer {server.create_access_token(self.admin['id'], self.admin['email'])}"}
        self.commercial_headers = {"Authorization": f"Bearer {server.create_access_token(self.commercial['id'], self.commercial['email'])}"}

    def tearDown(self):
        self.client.close()
        self.mongo.close()

    def _payload(self, **overrides):
        payload = {
            "title": "Réunion chantier", "date": "2026-11-04",
            "start_time": "09:00", "end_time": "10:30",
            "description": "Préparer les plans et les accès.",
            "location": "Agence de Lyon",
            "all_company": True, "participants": [],
            "show_on_dashboard": True, "send_notification": False,
        }
        payload.update(overrides)
        return payload

    def test_event_location_is_stored_and_visible_to_all_roles(self):
        created = self.client.post("/api/events", headers=self.admin_headers, json=self._payload())
        self.assertEqual(created.status_code, 200, created.text)
        event = created.json()
        self.assertEqual(event["location"], "Agence de Lyon")
        visible = self.client.get("/api/events?month=2026-11", headers=self.commercial_headers)
        self.assertEqual(visible.status_code, 200, visible.text)
        row = next(e for e in visible.json() if e["id"] == event["id"])
        self.assertEqual(row["description"], "Préparer les plans et les accès.")
        self.assertEqual(row["location"], "Agence de Lyon")
        self.assertEqual(row["start_time"], "09:00")

    def test_commercial_cannot_create_update_or_delete_event(self):
        self.assertEqual(self.client.post("/api/events", headers=self.commercial_headers, json=self._payload()).status_code, 403)
        created = self.client.post("/api/events", headers=self.admin_headers, json=self._payload()).json()
        self.assertEqual(self.client.put(f"/api/events/{created['id']}", headers=self.commercial_headers, json={"title": "Hack"}).status_code, 403)
        self.assertEqual(self.client.delete(f"/api/events/{created['id']}", headers=self.commercial_headers).status_code, 403)

    def test_admin_can_update_location(self):
        created = self.client.post("/api/events", headers=self.admin_headers, json=self._payload()).json()
        updated = self.client.put(f"/api/events/{created['id']}", headers=self.admin_headers, json={"location": "Salle 2"})
        self.assertEqual(updated.status_code, 200, updated.text)
        self.assertEqual(updated.json()["location"], "Salle 2")


if __name__ == "__main__":
    unittest.main()
