"""Hostile input and session lifecycle checks for KYLOT."""

from __future__ import annotations

import asyncio
import os
from datetime import datetime, timedelta, timezone
import unittest

import jwt


os.environ.update({
    "ENVIRONMENT": "production",
    "MONGO_URL": "mongodb://127.0.0.1:27017",
    "DB_NAME": "kylot_hostile_inputs",
    "JWT_SECRET": "hostile-input-test-secret-at-least-32-characters",
    "FRONTEND_URL": "https://app.example.invalid",
    "CORS_ORIGINS": "https://app.example.invalid",
    "ALLOW_PUBLIC_REGISTRATION": "false",
    "ALLOW_DEMO_DATA": "false",
    "ALLOW_TOKEN_RESPONSE": "false",
    "RUN_STARTUP_MIGRATIONS": "false",
    "EXPOSE_API_DOCS": "false",
    "COOKIE_SECURE": "true",
    "COOKIE_SAMESITE": "lax",
    "PHOTO_ALLOWED_HOSTS": "cdn.example.invalid",
})

from fastapi.testclient import TestClient
from mongomock_motor import AsyncMongoMockClient
from pydantic import ValidationError

from backend import server


def run(coro):
    return asyncio.run(coro)


class HostileInputAndSessionChecks(unittest.TestCase):
    def setUp(self):
        self.mongo = AsyncMongoMockClient()
        self.db = self.mongo["kylot_hostile_inputs"]
        server.db = self.db
        server.client = self.mongo
        self.client = TestClient(server.app)
        self.admin = {
            "id": "admin-a", "email": "admin-a@example.invalid", "name": "Admin A",
            "role": "admin", "company_id": "company-a",
            "permissions": server.get_default_permissions("admin"),
        }
        run(self.db.users.insert_one(self.admin))
        self.token = server.create_access_token(self.admin["id"], self.admin["email"])
        self.headers = {"Authorization": f"Bearer {self.token}"}

    def tearDown(self):
        self.client.close()
        self.mongo.close()

    def test_oversized_business_fields_are_rejected_before_storage(self):
        cases = [
            ("/api/clients", {"name": "A" * 201}),
            ("/api/prospects", {"name": "A" * 201}),
            ("/api/team", {"name": "A" * 121, "type": "commercial"}),
            ("/api/events", {"title": "Event", "date": "2026-10-19", "description": "A" * 5001}),
        ]
        for path, payload in cases:
            with self.subTest(path=path):
                response = self.client.post(path, headers=self.headers, json=payload)
                self.assertEqual(response.status_code, 422, response.text)
        self.assertEqual(run(self.db.clients.count_documents({})), 0)
        self.assertEqual(run(self.db.prospects.count_documents({})), 0)

    def test_nested_and_bulk_limits_are_enforced_by_models(self):
        with self.assertRaises(ValidationError):
            server.ProjectUpdate(assigned_to=["A"] * 101)
        with self.assertRaises(ValidationError):
            server.ProjectUpdate(assigned_to=["A" * 121])
        with self.assertRaises(ValidationError):
            server.ClientsBulkIn(text="A" * 1_000_001)
        with self.assertRaises(ValidationError):
            server.ClientsBulkIn(clients=[{"name": "A"}] * 5001)

    def test_settings_logo_reuses_the_hardened_image_validator(self):
        fake = "data:image/png;base64,ZXZpbA=="
        rejected = self.client.put("/api/settings", headers=self.headers, json={"logo": fake})
        self.assertEqual(rejected.status_code, 422, rejected.text)
        self.assertIsNone(run(self.db.settings.find_one({"company_id": "company-a"})))

        # 1x1 transparent PNG with a genuine PNG signature.
        valid = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
        accepted = self.client.put("/api/settings", headers=self.headers, json={"logo": valid})
        self.assertEqual(accepted.status_code, 200, accepted.text)

    def test_unapproved_remote_logo_is_rejected(self):
        rejected = self.client.put(
            "/api/settings", headers=self.headers,
            json={"logo": "https://tracking.attacker.invalid/pixel.png"},
        )
        self.assertEqual(rejected.status_code, 422, rejected.text)

    def test_expired_and_malformed_tokens_are_rejected(self):
        expired = jwt.encode({
            "sub": self.admin["id"], "email": self.admin["email"], "type": "access",
            "iat": int((datetime.now(timezone.utc) - timedelta(hours=2)).timestamp()),
            "exp": datetime.now(timezone.utc) - timedelta(hours=1),
        }, server.JWT_SECRET, algorithm=server.JWT_ALGORITHM)
        self.assertEqual(self.client.get("/api/auth/me", headers={"Authorization": f"Bearer {expired}"}).status_code, 401)
        self.assertEqual(self.client.get("/api/auth/me", headers={"Authorization": "Bearer not-a-jwt"}).status_code, 401)

    def test_deleted_user_token_is_rejected(self):
        run(self.db.users.delete_one({"id": self.admin["id"]}))
        self.assertEqual(self.client.get("/api/auth/me", headers=self.headers).status_code, 401)

    def test_logout_is_idempotent_and_revokes_the_token(self):
        self.assertEqual(self.client.post("/api/auth/logout", headers=self.headers).status_code, 200)
        self.assertEqual(self.client.post("/api/auth/logout", headers=self.headers).status_code, 200)
        self.assertEqual(self.client.get("/api/auth/me", headers=self.headers).status_code, 401)

    def test_unknown_fields_cannot_override_tenant_identity(self):
        response = self.client.post(
            "/api/clients", headers=self.headers,
            json={"name": "Client A", "company_id": "company-b", "created_by": "attacker"},
        )
        self.assertEqual(response.status_code, 200, response.text)
        stored = run(self.db.clients.find_one({"id": response.json()["id"]}))
        self.assertEqual(stored["company_id"], "company-a")
        self.assertEqual(stored["created_by"], "admin-a")


if __name__ == "__main__":
    unittest.main(verbosity=2)
