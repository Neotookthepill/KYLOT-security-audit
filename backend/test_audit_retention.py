"""Minimisation et rétention du journal d'audit."""

import asyncio
import os
import unittest

os.environ.update({
    "ENVIRONMENT": "production",
    "MONGO_URL": "mongodb://127.0.0.1:27017",
    "DB_NAME": "kylot_audit_retention_test",
    "JWT_SECRET": "audit-retention-secret-at-least-32-characters",
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


class AuditRetentionTests(unittest.TestCase):
    def setUp(self):
        self.mongo = AsyncMongoMockClient()
        self.db = self.mongo["kylot_audit_retention_test"]
        server.db = self.db
        server.client = self.mongo
        self.user = {
            "id": "audit-user", "email": "audit@example.com", "name": "Audit",
            "role": "admin", "company_id": "audit-company",
            "permissions": server.get_default_permissions("admin"),
        }

    def tearDown(self):
        self.mongo.close()

    def test_audit_redacts_secrets_and_photo_payloads(self):
        asyncio.run(server.log_audit(
            self.user, "update", "user", "audit-user",
            before={"password_hash": "secret", "token": "abc", "name": "Avant",
                    "photos": [{"src": "data:image/png;base64,AAAA"}]},
            after={"name": "Après", "notes": "x" * 2000, "nested": {"client_secret": "s"}},
        ))
        doc = asyncio.run(self.db.audit_log.find_one({"resource_id": "audit-user"}, {"_id": 0}))
        self.assertIsNotNone(doc)
        self.assertEqual(doc["before"]["password_hash"], "[masqué]")
        self.assertEqual(doc["before"]["token"], "[masqué]")
        self.assertEqual(doc["before"]["photos"], "[1 photo(s) masquée(s)]")
        self.assertEqual(doc["after"]["nested"]["client_secret"], "[masqué]")
        self.assertLessEqual(len(doc["after"]["notes"]), 500)
        self.assertIsNotNone(doc.get("at_dt"))


if __name__ == "__main__":
    unittest.main()
