"""Role matrix tests for the built-in operational roles."""

import asyncio
import os
import unittest

os.environ.update({
    "ENVIRONMENT": "production",
    "MONGO_URL": "mongodb://127.0.0.1:27017",
    "DB_NAME": "kylot_roles_test",
    "JWT_SECRET": "roles-test-secret-at-least-32-characters",
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


class RoleMatrixTests(unittest.TestCase):
    def setUp(self):
        self.mongo = AsyncMongoMockClient()
        self.db = self.mongo["kylot_roles_test"]
        server.db = self.db
        server.client = self.mongo
        self.client = TestClient(server.app, base_url="https://testserver")
        self.company = "company-a"
        self.admin = self._user("admin", "admin@example.com", "Admin", "admin")
        self.commercial = self._user("commercial", "commercial@example.com", "Commercial", "commercial")
        self.technicien = self._user("technicien", "technicien@example.com", "Technicien", "technicien")
        self.comptable = self._user("comptable", "comptable@example.com", "Comptable", "comptable")
        self.responsable = self._user("responsable", "responsable@example.com", "Responsable", "responsable")
        self.soustraitant = self._user("soustraitant", "soustraitant@example.com", "Sous-traitant", "sous_traitant")
        self.prospecteur = self._user("prospecteur", "prospecteur@example.com", "Prospecteur", "prospecteur")
        run(self.db.users.insert_many([
            self.admin, self.commercial, self.technicien, self.comptable,
            self.responsable, self.soustraitant, self.prospecteur,
        ]))
        run(self.db.clients.insert_one({"id": "client-a", "company_id": self.company, "name": "Client A"}))
        run(self.db.sales.insert_one({
            "id": "sale-a", "company_id": self.company, "client_id": "client-a",
            "service": "A", "amount": 100, "sale_date": "2026-11-01", "status": "en_cours",
            "commercial": "Commercial", "commercial_user_id": "commercial",
        }))
        run(self.db.projects.insert_one({
            "id": "project-a", "company_id": self.company, "sale_id": "sale-a",
            "client_id": "client-a", "service": "A", "scheduled_date": "2026-12-01",
            "assigned_to": ["Technicien"],
        }))
        self.headers = {name: self._headers(user) for name, user in {
            "admin": self.admin, "commercial": self.commercial, "technicien": self.technicien,
            "comptable": self.comptable, "responsable": self.responsable,
            "soustraitant": self.soustraitant, "prospecteur": self.prospecteur,
        }.items()}

    def tearDown(self):
        self.client.close()
        self.mongo.close()

    def _user(self, uid, email, name, role):
        return {
            "id": uid, "email": email, "name": name, "role": role,
            "company_id": self.company, "permissions": server.get_default_permissions(role),
            "password_hash": server.hash_password("V7!mQ2#pL9$xR4@t"), "is_active": True,
        }

    @staticmethod
    def _headers(user):
        return {"Authorization": f"Bearer {server.create_access_token(user['id'], user['email'])}"}

    def test_commercial_is_read_only_and_cannot_manage_users_or_settings(self):
        self.assertEqual(self.client.get("/api/sales?limit=10", headers=self.headers["commercial"]).status_code, 200)
        self.assertEqual(self.client.post("/api/sales", headers=self.headers["commercial"], json={
            "client_id": "client-a", "service": "X", "amount": 10, "sale_date": "2026-11-04", "status": "en_cours",
        }).status_code, 403)
        self.assertEqual(self.client.get("/api/users", headers=self.headers["commercial"]).status_code, 403)
        self.assertEqual(self.client.put("/api/settings", headers=self.headers["commercial"], json={"objectif_ca": 1000}).status_code, 403)

    def test_technicien_cannot_read_sales_or_clients_but_reads_projects(self):
        self.assertEqual(self.client.get("/api/sales?limit=10", headers=self.headers["technicien"]).status_code, 403)
        self.assertEqual(self.client.get("/api/clients?limit=10", headers=self.headers["technicien"]).status_code, 403)
        self.assertEqual(self.client.get("/api/projects?limit=10", headers=self.headers["technicien"]).status_code, 200)

    def test_comptable_reads_finance_but_cannot_create_sales(self):
        self.assertEqual(self.client.get("/api/sales?limit=10", headers=self.headers["comptable"]).status_code, 200)
        self.assertEqual(self.client.get("/api/clients?limit=10", headers=self.headers["comptable"]).status_code, 200)
        self.assertEqual(self.client.post("/api/sales", headers=self.headers["comptable"], json={
            "client_id": "client-a", "service": "X", "amount": 10, "sale_date": "2026-11-04", "status": "en_cours",
        }).status_code, 403)

    def test_responsable_cannot_manage_users_or_settings(self):
        self.assertEqual(self.client.get("/api/users", headers=self.headers["responsable"]).status_code, 403)
        self.assertEqual(self.client.put("/api/settings", headers=self.headers["responsable"], json={"objectif_ca": 1000}).status_code, 403)
        self.assertEqual(self.client.get("/api/sales?limit=10", headers=self.headers["responsable"]).status_code, 200)

    def test_soustraitant_and_prospecteur_have_no_sales_access(self):
        for name in ("soustraitant", "prospecteur"):
            self.assertEqual(self.client.get("/api/sales?limit=10", headers=self.headers[name]).status_code, 403, name)
            self.assertEqual(self.client.get("/api/clients?limit=10", headers=self.headers[name]).status_code, 403, name)


if __name__ == "__main__":
    unittest.main()
