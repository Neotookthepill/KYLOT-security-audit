"""Le mouvement de stock est persisté avec la mutation puis projeté."""

import asyncio
import os
import unittest

os.environ.update({
    "ENVIRONMENT": "production",
    "MONGO_URL": "mongodb://127.0.0.1:27017",
    "DB_NAME": "kylot_stock_outbox_test",
    "JWT_SECRET": "stock-outbox-secret-at-least-32-characters",
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

from mongomock_motor import AsyncMongoMockClient
from backend import server


class StockOutboxTests(unittest.TestCase):
    def setUp(self):
        self.mongo = AsyncMongoMockClient()
        self.db = self.mongo["kylot_stock_outbox_test"]
        server.db = self.db
        server.client = self.mongo
        self.user = {
            "id": "stock-admin", "email": "stock@example.com", "name": "Stock Admin",
            "role": "admin", "company_id": "stock-company",
            "permissions": server.get_default_permissions("admin"),
        }
        asyncio.run(self.db.stock.insert_one({
            "id": "stock-1", "company_id": "stock-company", "product_key": "cable",
            "product_name": "Câble", "stock_disponible": 10, "commande_en_cours": 0,
            "holders": [], "_rev": 0,
        }))

    def tearDown(self):
        self.mongo.close()

    def test_stock_and_movement_share_the_same_atomic_write_then_flush(self):
        def mutate(row):
            return ({"stock_disponible": int(row.get("stock_disponible") or 0) + 5}, {"qty": 5})

        def movement_factory(previous, _updates, _context):
            return server._log_movement(
                "stock-company", previous.get("product_key"), previous.get("product_name") or "",
                self.user, "receive", 5, None, None, None, "Réception test",
            )

        updated, _context, _previous = asyncio.run(
            server._stock_compare_and_set("stock-1", self.user, mutate, movement_factory=movement_factory)
        )
        self.assertEqual(updated["stock_disponible"], 15)
        self.assertEqual(asyncio.run(self.db.stock_movements.count_documents({})), 1)
        pending = asyncio.run(self.db.stock.find_one({"id": "stock-1"}, {"_id": 0, "pending_stock_movements": 1}))
        self.assertEqual(pending.get("pending_stock_movements") or [], [])

    def test_pending_movement_is_replayed_by_reading_stock(self):
        movement = server._log_movement(
            "stock-company", "cable", "Câble", self.user, "receive", 5, None, None, None, "pending",
        )
        asyncio.run(self.db.stock.update_one(
            {"id": "stock-1"}, {"$push": {"pending_stock_movements": movement}},
        ))
        asyncio.run(server._stock_flush_all_pending(self.user))
        self.assertEqual(asyncio.run(self.db.stock_movements.count_documents({})), 1)
        row = asyncio.run(self.db.stock.find_one({"id": "stock-1"}, {"_id": 0, "pending_stock_movements": 1}))
        self.assertEqual(row.get("pending_stock_movements") or [], [])


if __name__ == "__main__":
    unittest.main()
