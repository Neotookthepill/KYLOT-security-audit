"""Validation des entrées, formulaires, planning et import/export clients."""

import asyncio
import os
import unittest

os.environ.update({
    "ENVIRONMENT": "production",
    "MONGO_URL": "mongodb://127.0.0.1:27017",
    "DB_NAME": "kylot_forms_import_test",
    "JWT_SECRET": "forms-import-secret-at-least-32-characters",
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


class FormsImportTests(unittest.TestCase):
    def setUp(self):
        self.mongo = AsyncMongoMockClient()
        self.db = self.mongo["kylot_forms_import_test"]
        server.db = self.db
        server.client = self.mongo
        self.client = TestClient(server.app)
        self.admin_a = {
            "id": "admin-forms-a", "email": "forms-a@example.com", "name": "Forms A",
            "password_hash": server.hash_password("forms-password-a"),
            "role": "admin", "company_id": "company-forms-a",
            "permissions": server.get_default_permissions("admin"),
        }
        self.admin_b = {
            "id": "admin-forms-b", "email": "forms-b@example.com", "name": "Forms B",
            "password_hash": server.hash_password("forms-password-b"),
            "role": "admin", "company_id": "company-forms-b",
            "permissions": server.get_default_permissions("admin"),
        }
        asyncio.run(self.db.users.insert_many([self.admin_a, self.admin_b]))
        self.headers_a = {"Authorization": "Bearer " + server.create_access_token(self.admin_a["id"], self.admin_a["email"])}
        self.headers_b = {"Authorization": "Bearer " + server.create_access_token(self.admin_b["id"], self.admin_b["email"])}

    def tearDown(self):
        self.client.close()
        self.mongo.close()

    def test_client_sale_and_planning_inputs_are_bounded(self):
        cases = [
            ("post", "/api/clients", {"name": ""}),
            ("post", "/api/clients", {"name": "A" * 201}),
            ("post", "/api/clients", {"name": "Client", "notes": "x" * 5001}),
            ("post", "/api/sales", {"service": "S", "sale_date": "2026-02-31"}),
            ("post", "/api/sales", {"service": "S", "sale_date": "2026-11-10", "amount": -1}),
            ("post", "/api/sales", {"service": "S", "sale_date": "2026-11-10", "payment_installments": 0}),
            ("post", "/api/sales", {"service": "S", "sale_date": "2026-11-10", "commission_rate": 2}),
        ]
        for method, path, payload in cases:
            response = getattr(self.client, method)(path, headers=self.headers_a, json=payload)
            self.assertEqual(response.status_code, 422, f"{path} {payload}: {response.text}")

        asyncio.run(self.db.projects.insert_one({
            "id": "project-forms", "company_id": "company-forms-a", "client_id": "c",
            "assigned_to": [], "status": "en_cours", "scheduled_date": "2026-11-10",
        }))
        invalid = self.client.put(
            "/api/projects/project-forms", headers=self.headers_a,
            json={"scheduled_date": "2026-02-31"},
        )
        self.assertEqual(invalid.status_code, 422, invalid.text)

    def test_photo_source_and_import_mapping_are_rejected_when_invalid(self):
        asyncio.run(self.db.projects.insert_one({
            "id": "project-photo", "company_id": "company-forms-a", "client_id": "c",
            "assigned_to": [], "status": "en_cours", "scheduled_date": "2026-11-10", "photos": [],
        }))
        photo = self.client.post(
            "/api/projects/project-photo/photos", headers=self.headers_a,
            json={"photos": ["javascript:alert(1)"]},
        )
        self.assertEqual(photo.status_code, 422, photo.text)

        imported = self.client.post(
            "/api/clients/import/execute", headers=self.headers_a,
            json={"rows": [["0600000000"]], "mapping": {"0": "phone"}},
        )
        self.assertEqual(imported.status_code, 400, imported.text)

    def test_clients_csv_export_import_roundtrip_keeps_separate_address_fields(self):
        asyncio.run(self.db.clients.insert_one({
            "id": "client-source", "company_id": "company-forms-a", "name": "Client Source",
            "phone": "0600000001", "email": "source@example.invalid",
            "address": "12 Rue des Tilleuls", "postal_code": "59000", "city": "Lille",
            "notes": "Note source",
        }))
        exported = self.client.get("/api/export/clients.csv", headers=self.headers_a)
        self.assertEqual(exported.status_code, 200, exported.text)
        csv_bytes = exported.content
        self.assertIn("Adresse", csv_bytes.decode("utf-8"))
        self.assertIn("Code postal", csv_bytes.decode("utf-8"))
        self.assertIn("Ville", csv_bytes.decode("utf-8"))

        parsed = self.client.post(
            "/api/clients/import/parse", headers=self.headers_b,
            files={"file": ("clients.csv", csv_bytes, "text/csv")},
        )
        self.assertEqual(parsed.status_code, 200, parsed.text)
        body = parsed.json()
        self.assertGreaterEqual(body["row_count"], 1)

        executed = self.client.post(
            "/api/clients/import/execute", headers=self.headers_b,
            json={
                "import_id": body["import_id"],
                "mapping": body["auto_mapping"],
                "duplicate_strategy": "create",
            },
        )
        self.assertEqual(executed.status_code, 200, executed.text)
        source = asyncio.run(self.db.clients.find_one(
            {"company_id": "company-forms-b", "name": "Client Source"}, {"_id": 0}
        ))
        self.assertIsNotNone(source)
        self.assertEqual(source["address"], "12 Rue des Tilleuls")
        self.assertEqual(source["postal_code"], "59000")
        self.assertEqual(source["city"], "Lille")
        self.assertEqual(source["phone"], "0600000001")


if __name__ == "__main__":
    unittest.main()
