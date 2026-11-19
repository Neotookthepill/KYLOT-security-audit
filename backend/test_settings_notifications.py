import asyncio
import os
import unittest

os.environ.update({
    "ENVIRONMENT": "production", "MONGO_URL": "mongodb://127.0.0.1:27017",
    "DB_NAME": "kylot_settings_notifications_test", "JWT_SECRET": "settings-notif-test-key-8f2c5d7a1e9b3c4d",
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


class SettingsNotificationsTests(unittest.TestCase):
    def setUp(self):
        self.mongo = AsyncMongoMockClient(); self.db = self.mongo["kylot_settings_notifications_test"]
        server.db = self.db; server.client = self.mongo; self.client = TestClient(server.app)
        self.user = {"id": "admin-1", "email": "admin@example.com", "name": "Admin", "role": "admin",
                     "company_id": "company-1", "permissions": server.get_default_permissions("admin")}
        run(self.db.users.insert_one(self.user))
        self.headers = {"Authorization": f"Bearer {server.create_access_token(self.user['id'], self.user['email'])}"}

    def tearDown(self):
        self.client.close(); self.mongo.close()

    def test_14j_notification_setting_is_accepted(self):
        r = self.client.put("/api/settings", headers=self.headers,
                            json={"notifications": {"attente_14j_jourj_notif": True}})
        self.assertEqual(r.status_code, 200, r.text)
        saved = run(self.db.settings.find_one({"company_id": "company-1", "kind": "global"}))
        self.assertTrue((saved or {}).get("notifications", {}).get("attente_14j_jourj_notif"))


if __name__ == "__main__":
    unittest.main()
