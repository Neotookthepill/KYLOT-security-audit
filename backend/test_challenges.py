"""Tests for the commercial Challenge module (v1, source-based criteria)."""

import os
import unittest

os.environ.update({
    "ENVIRONMENT": "production",
    "MONGO_URL": "mongodb://127.0.0.1:27017",
    "DB_NAME": "kylot_challenge_test",
    "JWT_SECRET": "challenge-test-key-7c1b5e9a3d2f8c4b",
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


class ChallengeTests(unittest.TestCase):
    def setUp(self):
        self.mongo = AsyncMongoMockClient()
        self.db = self.mongo["kylot_challenge_test"]
        server.db = self.db
        server.client = self.mongo
        self.client = TestClient(server.app, base_url="https://testserver")
        self.admin = {
            "id": "admin-challenge", "email": "admin@example.com", "name": "Admin",
            "role": "admin", "company_id": "company-a",
            "permissions": server.get_default_permissions("admin"),
            "password_hash": server.hash_password("V7!mQ2#pL9$xR4@t"),
            "is_active": True,
        }
        self.commercial = {
            "id": "commercial-a", "email": "a@example.com", "name": "Commercial A",
            "role": "commercial", "company_id": "company-a",
            "permissions": server.get_default_permissions("commercial"),
            "password_hash": server.hash_password("V7!mQ2#pL9$xR4@t"),
            "is_active": True,
        }
        run(self.db.users.insert_many([self.admin, self.commercial]))
        run(self.db.sales.insert_many([
            {"id": "s-a1", "company_id": "company-a", "commercial": "Commercial A",
             "source": "Assist", "status": "en_cours", "amount": 1000,
             "sale_date": "2026-11-05"},
            {"id": "s-a2", "company_id": "company-a", "commercial": "Commercial A",
             "source": "Assist", "status": "annule", "amount": 500,
             "sale_date": "2026-11-06"},
            {"id": "s-b1", "company_id": "company-a", "commercial": "Commercial B",
             "source": "Assist", "status": "en_cours", "amount": 2000,
             "sale_date": "2026-11-07"},
            {"id": "s-r1", "company_id": "company-a", "commercial": "Commercial A",
             "source": "R1", "status": "en_cours", "amount": 3000,
             "sale_date": "2026-11-08"},
        ]))
        self.admin_headers = {"Authorization": f"Bearer {server.create_access_token(self.admin['id'], self.admin['email'])}"}
        self.commercial_headers = {"Authorization": f"Bearer {server.create_access_token(self.commercial['id'], self.commercial['email'])}"}

    def tearDown(self):
        self.client.close()
        self.mongo.close()

    def _payload(self):
        return {
            "name": "Challenge de Noël 2026",
            "start_date": "2026-11-01",
            "end_date": "2026-12-17",
            "criterion": "assist",
            "participant_names": ["Commercial A", "Commercial B"],
            "rewards": [
                {"place": 1, "amount": 1250},
                {"place": 2, "amount": 500},
                {"place": 3, "amount": 250},
            ],
        }

    def test_create_and_rank_assistances(self):
        created = self.client.post("/api/challenges", headers=self.admin_headers, json=self._payload())
        self.assertEqual(created.status_code, 200, created.text)
        current = self.client.get("/api/challenges/current", headers=self.commercial_headers)
        self.assertEqual(current.status_code, 200, current.text)
        body = current.json()
        self.assertEqual(body["challenge"]["name"], "Challenge de Noël 2026")
        ranking = {row["name"]: row for row in body["ranking"]}
        self.assertEqual(ranking["Commercial A"]["count"], 1)
        self.assertEqual(ranking["Commercial B"]["count"], 1)
        self.assertEqual(ranking["Commercial A"]["rank"], 1)
        self.assertEqual(ranking["Commercial B"]["rank"], 1)

    def test_only_admin_can_create_and_one_active_challenge(self):
        denied = self.client.post("/api/challenges", headers=self.commercial_headers, json=self._payload())
        self.assertEqual(denied.status_code, 403, denied.text)
        self.client.post("/api/challenges", headers=self.admin_headers, json=self._payload())
        duplicate = self.client.post("/api/challenges", headers=self.admin_headers, json=self._payload())
        self.assertEqual(duplicate.status_code, 409, duplicate.text)

    def test_sales_outside_the_challenge_period_are_excluded(self):
        run(self.db.sales.insert_one({
            "id": "s-outside", "company_id": "company-a", "commercial": "Commercial A",
            "source": "Assist", "status": "en_cours", "amount": 9999,
            "sale_date": "2027-01-15",
        }))
        created = self.client.post("/api/challenges", headers=self.admin_headers, json=self._payload())
        self.assertEqual(created.status_code, 200, created.text)
        body = self.client.get("/api/challenges/current", headers=self.commercial_headers).json()
        ranking = {row["name"]: row for row in body["ranking"]}
        self.assertEqual(ranking["Commercial A"]["count"], 1)

    def test_ca_criterion_uses_amounts_and_ignores_cancelled_sales(self):
        payload = self._payload()
        payload["name"] = "Challenge CA"
        payload["criterion"] = "ca"
        created = self.client.post("/api/challenges", headers=self.admin_headers, json=payload)
        self.assertEqual(created.status_code, 200, created.text)
        body = self.client.get("/api/challenges/current", headers=self.commercial_headers).json()
        ranking = {row["name"]: row for row in body["ranking"]}
        self.assertEqual(ranking["Commercial A"]["ca"], 4000)
        self.assertEqual(ranking["Commercial A"]["points"], 4000)
        self.assertEqual(ranking["Commercial B"]["ca"], 2000)

    def test_close_keeps_a_snapshot_in_history(self):
        created = self.client.post("/api/challenges", headers=self.admin_headers, json=self._payload())
        cid = created.json()["id"]
        closed = self.client.post(f"/api/challenges/{cid}/close", headers=self.admin_headers)
        self.assertEqual(closed.status_code, 200, closed.text)
        self.assertIn("results_snapshot", closed.json()["challenge"])
        history = self.client.get("/api/challenges?include_closed=1", headers=self.admin_headers)
        self.assertEqual(history.status_code, 200, history.text)
        self.assertTrue(history.json()[0]["results_snapshot"]["ranking"])
        current = self.client.get("/api/challenges/current", headers=self.commercial_headers)
        self.assertIsNone(current.json()["challenge"])


if __name__ == "__main__":
    unittest.main()
