"""Régression : création technicien + ajout immédiat de quantité."""

import asyncio
import os
import unittest

os.environ.update({
    "ENVIRONMENT": "production",
    "MONGO_URL": "mongodb://127.0.0.1:27017",
    "DB_NAME": "kylot_tech_stock_test",
    "JWT_SECRET": "tech-stock-secret-at-least-32-characters",
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


class TechStockCreateTests(unittest.TestCase):
    def setUp(self):
        self.mongo = AsyncMongoMockClient()
        self.db = self.mongo["kylot_tech_stock_test"]
        server.db = self.db
        server.client = self.mongo
        self.client = TestClient(server.app)
        self.tech = {
            "id": "tech-stock", "email": "tech-stock@example.com", "name": "Tech Stock",
            "password_hash": server.hash_password("tech-stock-password"), "role": "technicien",
            "company_id": "company-tech", "permissions": server.get_default_permissions("technicien"),
        }
        asyncio.run(self.db.users.insert_one(self.tech))
        self.headers = {"Authorization": "Bearer " + server.create_access_token(self.tech["id"], self.tech["email"])}

    def tearDown(self):
        self.client.close()
        self.mongo.close()

    def test_new_product_actually_adds_quantity_and_retry_does_not_duplicate(self):
        payload = {"product_name": "Produit technicien test", "qty": 7, "client_request_id": "tech-create-request-1"}
        first = self.client.post("/api/stock/tech-create-and-hold", headers=self.headers, json=payload)
        self.assertEqual(first.status_code, 200, first.text)
        row = asyncio.run(self.db.stock.find_one({"product_key": "produit technicien test"}, {"_id": 0}))
        self.assertIsNotNone(row)
        my_holder = next(h for h in row["holders"] if h["user_id"] == "tech-stock")
        self.assertEqual(my_holder["qty"], 7)
        self.assertIn("tech-create-request-1", row.get("applied_stock_requests") or [])

        replay = self.client.post("/api/stock/tech-create-and-hold", headers=self.headers, json=payload)
        self.assertEqual(replay.status_code, 200, replay.text)
        row = asyncio.run(self.db.stock.find_one({"product_key": "produit technicien test"}, {"_id": 0}))
        self.assertEqual(next(h for h in row["holders"] if h["user_id"] == "tech-stock")["qty"], 7)


if __name__ == "__main__":
    unittest.main()
