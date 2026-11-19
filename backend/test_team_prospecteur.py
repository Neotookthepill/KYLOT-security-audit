import asyncio
import os
import unittest

os.environ.update({
    "ENVIRONMENT": "production", "MONGO_URL": "mongodb://127.0.0.1:27017",
    "DB_NAME": "kylot_team_prospecteur_test", "JWT_SECRET": "team-prospecteur-test-key-4a8c2e7f1b9d3c5e",
    "FRONTEND_URL": "https://app.example.invalid", "CORS_ORIGINS": "https://app.example.invalid",
    "ALLOW_PUBLIC_REGISTRATION": "false", "ALLOW_DEMO_DATA": "false",
    "ALLOW_TOKEN_RESPONSE": "false", "RUN_STARTUP_MIGRATIONS": "false",
    "EXPOSE_API_DOCS": "false", "COOKIE_SECURE": "true", "COOKIE_SAMESITE": "lax",
    "ADMIN_EMAIL": "admin@example.com", "ADMIN_PASSWORD": "V7!mQ2#pL9$xR4@t",
})
from fastapi.testclient import TestClient
from mongomock_motor import AsyncMongoMockClient
from backend import server


def run(coro): return asyncio.run(coro)


class TeamProspecteurTests(unittest.TestCase):
    def setUp(self):
        self.mongo = AsyncMongoMockClient(); self.db = self.mongo["kylot_team_prospecteur_test"]
        server.db = self.db; server.client = self.mongo; self.client = TestClient(server.app)
        self.admin = {"id": "admin-1", "email": "admin@example.com", "name": "Admin",
                      "role": "admin", "company_id": "company-1",
                      "subscription_plan": "keylot_entreprise_monthly",
                      "permissions": server.get_default_permissions("admin")}
        run(self.db.users.insert_one(self.admin))
        run(self.db.clients.insert_one({"id": "client-p", "company_id": "company-1", "name": "Client P"}))
        self.headers = {"Authorization": "Bearer " + server.create_access_token(self.admin["id"], self.admin["email"])}

    def tearDown(self):
        self.client.close(); self.mongo.close()

    def test_prospecteur_without_account_can_be_added_and_invited(self):
        r = self.client.post("/api/team", headers=self.headers,
                             json={"name": "Prospect Sans Compte", "type": "prospecteur", "email": ""})
        self.assertEqual(r.status_code, 200, r.text)
        member = r.json()
        self.assertIsNone(member.get("user_id"))
        prospects = self.client.get("/api/prospecteurs", headers=self.headers)
        self.assertIn(member["id"], [x["id"] for x in prospects.json()])

        # Vente associée à la fiche sans compte
        sale = self.client.post("/api/sales", headers=self.headers, json={
            "bdc": "P-1", "client_id": "client-p", "client_name": "Client P", "service": "Test", "amount": 1000, "sale_date": "2026-11-19",
            "status": "en_cours", "prospecteur_id": member["id"],
        })
        self.assertEqual(sale.status_code, 200, sale.text)

        inv = self.client.post(f"/api/team/{member['id']}/invite", headers=self.headers,
                               json={"email": "prospect@example.com"})
        self.assertEqual(inv.status_code, 200, inv.text)
        self.assertTrue(inv.json().get("invite_url"))
        linked = run(self.db.team_members.find_one({"id": member["id"]}))
        self.assertIsNotNone(linked)
        migrated = run(self.db.sales.find_one({"bdc": "P-1"}))
        self.assertEqual(migrated.get("prospecteur_id"), linked["user_id"])


if __name__ == "__main__":
    unittest.main()
