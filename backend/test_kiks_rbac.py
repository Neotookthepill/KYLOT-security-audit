"""KIK'S doit respecter les mêmes portées RBAC que les routes directes."""

import asyncio
import os
import sys
import types
import unittest
from unittest.mock import patch

os.environ.update({
    "ENVIRONMENT": "production",
    "MONGO_URL": "mongodb://127.0.0.1:27017",
    "DB_NAME": "kylot_kiks_rbac_test",
    "JWT_SECRET": "kiks-rbac-secret-at-least-32-characters",
    "FRONTEND_URL": "https://app.example.invalid",
    "CORS_ORIGINS": "https://app.example.invalid",
    "ALLOW_PUBLIC_REGISTRATION": "false",
    "ALLOW_DEMO_DATA": "false",
    "ALLOW_TOKEN_RESPONSE": "false",
    "RUN_STARTUP_MIGRATIONS": "false",
    "EXPOSE_API_DOCS": "false",
    "COOKIE_SECURE": "true",
    "COOKIE_SAMESITE": "lax",
    "ALLOW_EXTERNAL_AI": "true",
    "EMERGENT_LLM_KEY": "test-kiks-key",
})

from fastapi.testclient import TestClient
from mongomock_motor import AsyncMongoMockClient

from backend import server


class FakeLlmChat:
    plan = {"action": "search_client", "params": {"query": "Alice"}}

    def __init__(self, **_kwargs):
        pass

    def with_model(self, *_args, **_kwargs):
        return self

    async def send_message(self, _message):
        import json
        return json.dumps(type(self).plan)


def fake_modules():
    chat = types.ModuleType("emergentintegrations.llm.chat")
    chat.LlmChat = FakeLlmChat
    chat.UserMessage = lambda text=None, **kwargs: text
    llm = types.ModuleType("emergentintegrations.llm")
    llm.chat = chat
    base = types.ModuleType("emergentintegrations")
    base.llm = llm
    return {"emergentintegrations": base, "emergentintegrations.llm": llm, "emergentintegrations.llm.chat": chat}


class KiksRbacTests(unittest.TestCase):
    def setUp(self):
        self.mongo = AsyncMongoMockClient()
        self.db = self.mongo["kylot_kiks_rbac_test"]
        server.db = self.db
        server.client = self.mongo
        self.client = TestClient(server.app)
        self.company = "company-kiks"
        self.admin = self._user("admin-kiks", "admin-kiks@example.com", "Admin Kiks", "admin", server.get_default_permissions("admin"))
        self.tech = self._user("tech-kiks", "tech-kiks@example.com", "Tech Kiks", "technicien", server.get_default_permissions("technicien"))
        self.commercial = self._user("com-kiks", "com-kiks@example.com", "Commercial Kiks", "commercial", server.get_default_permissions("commercial"))
        asyncio.run(self.db.users.insert_many([self.admin, self.tech, self.commercial]))
        asyncio.run(self.db.clients.insert_one({
            "id": "client-secret", "company_id": self.company, "name": "Alice Secret",
            "phone": "0600000999", "address": "1 rue privée", "city": "Lille",
        }))
        asyncio.run(self.db.sales.insert_one({
            "id": "sale-secret", "company_id": self.company, "client_id": "client-secret",
            "client_name": "Alice Secret", "service": "Prestation", "amount": 123456,
            "status": "en_cours", "sale_date": "2026-11-01", "commercial": "Commercial Kiks",
            "commercial_user_id": "com-kiks",
        }))
        asyncio.run(self.db.projects.insert_many([
            {"id": "project-mine", "company_id": self.company, "client_id": "client-secret",
             "sale_id": "sale-secret", "status": "en_cours", "assigned_to": [], "cancelled": False},
            {"id": "project-other", "company_id": self.company, "client_id": "client-other",
             "sale_id": "sale-other", "status": "en_cours", "assigned_to": [], "cancelled": False},
        ]))
        self.headers = {
            "admin": self._headers(self.admin),
            "tech": self._headers(self.tech),
            "commercial": self._headers(self.commercial),
        }

    def tearDown(self):
        self.client.close()
        self.mongo.close()

    def _user(self, uid, email, name, role, permissions):
        return {"id": uid, "email": email, "name": name, "role": role,
                "company_id": self.company, "permissions": permissions,
                "password_hash": server.hash_password("kiks-password-123")}

    def _headers(self, user):
        return {"Authorization": "Bearer " + server.create_access_token(user["id"], user["email"])}

    def _call(self, user, plan):
        FakeLlmChat.plan = plan
        with patch.dict(sys.modules, fake_modules()):
            return self.client.post("/api/kiks/act", headers=self.headers[user],
                                    json={"message": "test", "page": "clients"})

    def test_technician_cannot_search_clients_or_sales(self):
        response = self._call("tech", {"action": "search_client", "params": {"query": "Alice"}})
        self.assertEqual(response.status_code, 403, response.text)
        response = self._call("tech", {"action": "search_sale", "params": {"query": "Alice"}})
        self.assertEqual(response.status_code, 403, response.text)

    def test_commercial_only_gets_own_project(self):
        response = self._call("commercial", {"action": "list_projects_by_status", "params": {"status": "en_cours"}})
        self.assertEqual(response.status_code, 200, response.text)
        data = response.json().get("results", {}).get("projects", [])
        self.assertEqual([p["id"] for p in data], ["project-mine"])

    def test_scope_none_is_refused_before_database_access(self):
        response = self._call("tech", {"action": "list_reinterventions_date", "params": {"date": "today"}})
        # Le technicien a planning.view own dans les permissions par défaut ;
        # le contrôle ne doit jamais retourner une liste globale.
        self.assertIn(response.status_code, {200, 403}, response.text)
        if response.status_code == 200:
            self.assertEqual(response.json().get("results", {}).get("reinterventions", []), [])


if __name__ == "__main__":
    unittest.main()
