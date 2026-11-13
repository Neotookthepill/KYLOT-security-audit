"""Synchronisation vente → chantier/planning et techniciens dans la recherche."""

import asyncio
import os
import unittest

os.environ.update({
    "ENVIRONMENT": "production",
    "MONGO_URL": "mongodb://127.0.0.1:27017",
    "DB_NAME": "kylot_sale_project_sync_test",
    "JWT_SECRET": "sale-project-sync-secret-at-least-32-characters",
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


class SaleProjectSyncTests(unittest.TestCase):
    def setUp(self):
        self.mongo = AsyncMongoMockClient()
        self.db = self.mongo["kylot_sale_project_sync_test"]
        server.db = self.db
        server.client = self.mongo
        self.client = TestClient(server.app)
        self.admin = {
            "id": "admin-sync", "email": "admin-sync@example.com", "name": "Admin Sync",
            "password_hash": server.hash_password("sync-password-123"),
            "role": "admin", "company_id": "company-sync",
            "permissions": server.get_default_permissions("admin"),
        }
        asyncio.run(self.db.users.insert_one(self.admin))
        asyncio.run(self.db.clients.insert_one({
            "id": "client-sync", "company_id": "company-sync", "name": "Client Synchro",
            "phone": "0327376451 / 0612569563", "city": "Méru", "postal_code": "60200",
        }))
        asyncio.run(self.db.sales.insert_one({
            "id": "sale-sync", "company_id": "company-sync", "client_id": "client-sync",
            "client_name": "Client Synchro", "service": "Mise en sécurité", "amount": 1000,
            "sale_date": "2026-11-01", "status": "attente_fi",
            "desired_intervention_date": None, "commercial": "Admin Sync",
            "source": "R1", "commission_rate": 0.1,
        }))
        asyncio.run(self.db.projects.insert_one({
            "id": "project-sync", "company_id": "company-sync", "sale_id": "sale-sync",
            "client_id": "client-sync", "status": "a_planifier", "scheduled_date": None,
            "assigned_to": ["Alice Martin", "Bob Durand"], "cancelled": False,
        }))
        self.headers = {"Authorization": "Bearer " + server.create_access_token(self.admin["id"], self.admin["email"])}

    def tearDown(self):
        self.client.close()
        self.mongo.close()

    def test_sale_date_programs_existing_project_without_duplicate(self):
        first = self.client.put(
            "/api/sales/sale-sync", headers=self.headers,
            json={"desired_intervention_date": "2026-11-20"},
        )
        self.assertEqual(first.status_code, 200, first.text)
        projects = asyncio.run(self.db.projects.find({"sale_id": "sale-sync"}, {"_id": 0}).to_list(10))
        self.assertEqual(len(projects), 1)
        self.assertEqual(projects[0]["status"], "en_cours")
        self.assertEqual(projects[0]["scheduled_date"], "2026-11-20")

        second = self.client.put(
            "/api/sales/sale-sync", headers=self.headers,
            json={"desired_intervention_date": "2026-11-22"},
        )
        self.assertEqual(second.status_code, 200, second.text)
        projects = asyncio.run(self.db.projects.find({"sale_id": "sale-sync"}, {"_id": 0}).to_list(10))
        self.assertEqual(len(projects), 1)
        self.assertEqual(projects[0]["scheduled_date"], "2026-11-22")

    def test_existing_stale_project_is_repaired_on_list(self):
        asyncio.run(self.db.sales.update_one(
            {"id": "sale-sync"}, {"$set": {"desired_intervention_date": "2026-11-25"}},
        ))
        response = self.client.post("/api/admin/projects/repair-dates", headers=self.headers)
        self.assertEqual(response.status_code, 200, response.text)
        project = asyncio.run(self.db.projects.find_one({"id": "project-sync"}, {"_id": 0}))
        self.assertEqual(project["status"], "en_cours")
        self.assertEqual(project["scheduled_date"], "2026-11-25")


    def test_stale_project_with_real_date_is_promoted_even_without_sale_date(self):
        asyncio.run(self.db.sales.update_one(
            {"id": "sale-sync"}, {"$set": {"desired_intervention_date": None}},
        ))
        asyncio.run(self.db.projects.update_one(
            {"id": "project-sync"}, {"$set": {"scheduled_date": "2026-12-03"}},
        ))
        response = self.client.post("/api/admin/projects/repair-dates", headers=self.headers)
        self.assertEqual(response.status_code, 200, response.text)
        project = asyncio.run(self.db.projects.find_one({"id": "project-sync"}, {"_id": 0}))
        self.assertEqual(project["status"], "en_cours")
        self.assertEqual(project["scheduled_date"], "2026-12-03")

    def test_client_search_returns_all_technicians(self):
        asyncio.run(self.db.sales.update_one(
            {"id": "sale-sync"}, {"$set": {"desired_intervention_date": "2026-11-25"}},
        ))
        response = self.client.get("/api/search?q=Synchro", headers=self.headers)
        self.assertEqual(response.status_code, 200, response.text)
        clients = response.json()["categories"]["clients"]
        self.assertTrue(clients)
        self.assertEqual(clients[0]["technicians"], ["Alice Martin", "Bob Durand"])
        self.assertEqual(clients[0]["technician_label"], "Alice Martin, Bob Durand")



    def test_projects_endpoint_applies_server_search_and_status(self):
        asyncio.run(self.db.projects.insert_one({
            "id": "project-other", "company_id": "company-sync", "sale_id": "sale-sync",
            "client_id": "client-sync", "status": "en_cours", "scheduled_date": "2026-11-26",
            "assigned_to": ["Alice Martin"], "cancelled": False, "service": "Autre",
        }))
        response = self.client.get(
            "/api/projects?status=a_planifier&q=Synchro&limit=1&offset=0",
            headers=self.headers,
        )
        self.assertEqual(response.status_code, 200, response.text)
        rows = response.json()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["id"], "project-sync")

    def test_clients_list_returns_technicians_too(self):
        response = self.client.get("/api/clients?q=Synchro", headers=self.headers)
        self.assertEqual(response.status_code, 200, response.text)
        rows = response.json()
        self.assertTrue(rows)
        self.assertEqual(rows[0]["technicians"], ["Alice Martin", "Bob Durand"])
        self.assertEqual(rows[0]["technician_label"], "Alice Martin, Bob Durand")

    def test_client_search_labels_unassigned(self):
        asyncio.run(self.db.projects.update_one({"id": "project-sync"}, {"$set": {"assigned_to": []}}))
        response = self.client.get("/api/search?q=Synchro", headers=self.headers)
        self.assertEqual(response.status_code, 200, response.text)
        clients = response.json()["categories"]["clients"]
        self.assertTrue(clients)
        self.assertEqual(clients[0]["technician_label"], "Technicien non attribué")


if __name__ == "__main__":
    unittest.main()
