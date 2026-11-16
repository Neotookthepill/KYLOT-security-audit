"""Invitations admin : création inactive, lien unique, activation, connexion."""

import asyncio
import os
import unittest
from urllib.parse import urlparse, parse_qs

os.environ.update({
    "ENVIRONMENT": "production",
    "MONGO_URL": "mongodb://127.0.0.1:27017",
    "DB_NAME": "kylot_invitation_test",
    "JWT_SECRET": "invitation-test-secret-at-least-32-characters",
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


class InvitationTests(unittest.TestCase):
    def setUp(self):
        self.mongo = AsyncMongoMockClient()
        self.db = self.mongo["kylot_invitation_test"]
        server.db = self.db
        server.client = self.mongo
        self.client = TestClient(server.app)
        self.admin = {
            "id": "admin-invite", "email": "admin-invite@example.com", "name": "Admin Invite",
            "password_hash": server.hash_password("invite-admin-123"),
            "role": "admin", "company_id": "company-invite",
            "permissions": server.get_default_permissions("admin"),
        }
        asyncio.run(self.db.users.insert_one(self.admin))
        self.headers = {"Authorization": "Bearer " + server.create_access_token(self.admin["id"], self.admin["email"])}

    def tearDown(self):
        self.client.close()
        self.mongo.close()

    def test_invite_accept_and_login(self):
        created = self.client.post("/api/users/invite", headers=self.headers, json={
            "name": "Invité Test", "email": "invite-test@qylot-audit.com", "role": "commercial",
        })
        self.assertEqual(created.status_code, 200, created.text)
        data = created.json()
        self.assertIn("invite_url", data)
        token = parse_qs(urlparse(data["invite_url"]).query).get("token", [""])[0]
        self.assertTrue(token)

        user = asyncio.run(self.db.users.find_one({"email": "invite-test@qylot-audit.com"}))
        self.assertFalse(user["is_active"])
        self.assertTrue(user["invite_pending"])

        preview = self.client.get(f"/api/auth/invitation/{token}")
        self.assertEqual(preview.status_code, 200, preview.text)
        self.assertEqual(preview.json()["email"], "invite-test@qylot-audit.com")

        accepted = self.client.post("/api/auth/accept-invitation", json={
            "token": token, "password": "mot-de-passe-invite-123",
        })
        self.assertEqual(accepted.status_code, 200, accepted.text)
        user = asyncio.run(self.db.users.find_one({"email": "invite-test@qylot-audit.com"}))
        self.assertTrue(user["is_active"])
        self.assertFalse(user["invite_pending"])

        login = self.client.post("/api/auth/login", json={
            "email": "invite-test@qylot-audit.com", "password": "mot-de-passe-invite-123",
        })
        self.assertEqual(login.status_code, 200, login.text)

        replay = self.client.post("/api/auth/accept-invitation", json={
            "token": token, "password": "mot-de-passe-invite-123",
        })
        self.assertGreaterEqual(replay.status_code, 400)

    def test_invite_duplicate_email_and_non_admin(self):
        payload = {"name": "Invité Test 2", "email": "invite-test-2@qylot-audit.com", "role": "technicien"}
        self.assertEqual(self.client.post("/api/users/invite", headers=self.headers, json=payload).status_code, 200)
        self.assertEqual(self.client.post("/api/users/invite", headers=self.headers, json=payload).status_code, 400)
        self.assertEqual(self.client.post("/api/users/invite", json=payload).status_code, 401)
