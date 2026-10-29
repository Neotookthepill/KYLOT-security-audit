"""High-value multi-role and multi-tenant HTTP matrix for KYLOT.

The suite runs in-process against a disposable Mongo-compatible database. It
does not replace browser/staging tests, but it makes direct-ID cross-company
regressions and role escalation reproducible in CI.
"""

from __future__ import annotations

import asyncio
import os
import unittest


os.environ.update({
    "ENVIRONMENT": "production",
    "MONGO_URL": "mongodb://127.0.0.1:27017",
    "DB_NAME": "kylot_e2e_matrix",
    "JWT_SECRET": "matrix-test-secret-at-least-32-characters",
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


class MultiTenantHTTPMatrix(unittest.TestCase):
    def setUp(self):
        self.mongo = AsyncMongoMockClient()
        self.db = self.mongo["kylot_e2e_matrix"]
        server.db = self.db
        server.client = self.mongo
        self.client = TestClient(server.app)

        self.users = [
            self._user("admin-a", "admin", "company-a", "Admin A"),
            self._user("admin-b", "admin", "company-b", "Admin B"),
            self._user("responsable-a", "responsable", "company-a", "Responsable A"),
            self._user("commercial-a", "commercial", "company-a", "Commercial A"),
            self._user("tech-a", "technicien", "company-a", "Technicien A"),
            self._user("super", "super_admin", "platform", "Super Admin"),
        ]
        run(self.db.users.insert_many(self.users))
        self.headers = {u["id"]: self._headers(u) for u in self.users}
        self._seed_company_b()

    def tearDown(self):
        self.client.close()
        self.mongo.close()

    @staticmethod
    def _user(uid: str, role: str, company: str, name: str) -> dict:
        return {
            "id": uid,
            "email": f"{uid}@example.invalid",
            "name": name,
            "role": role,
            "company_id": company,
            "permissions": server.get_default_permissions(role),
        }

    @staticmethod
    def _headers(user: dict) -> dict:
        token = server.create_access_token(user["id"], user["email"])
        return {"Authorization": f"Bearer {token}"}

    def _seed_company_b(self):
        b = "company-b"
        collections = {
            "clients": [{"id": "client-b", "company_id": b, "name": "Client B"}],
            "sales": [{
                "id": "sale-b", "company_id": b, "client_id": "client-b",
                "commercial": "Admin B", "commercial_user_id": "admin-b",
                "sale_date": "2026-10-01", "service": "Service B", "amount": 100,
                "prospecteur_id": "prospecteur-b",
            }],
            "projects": [{
                "id": "project-b", "company_id": b, "client_id": "client-b",
                "sale_id": "sale-b", "assigned_to": ["Admin B"],
                "status": "a_planifier", "scheduled_date": "2026-10-01",
                "duration_days": 1, "photos": [], "cancelled": True,
            }],
            "client_notes": [{"id": "client-note-b", "company_id": b, "client_id": "client-b", "text": "B"}],
            "project_notes": [{
                "id": "project-note-b", "company_id": b, "project_id": "project-b",
                "technician_name": "Admin B", "technician_name_lc": "admin b", "note": "B",
            }],
            "ai_corrections": [{"id": "correction-b", "company_id": b, "field": "name"}],
            "ai_memories": [{
                "id": "memory-b", "company_id": b, "scope": "company",
                "user_id": None, "content": "Secret B",
            }],
            "team_members": [{"id": "team-b", "company_id": b, "name": "Member B", "type": "commercial"}],
            "bonuses": [{"id": "bonus-b", "company_id": b, "name": "Bonus B", "amount": 10}],
            "project_bonuses": [{
                "id": "project-bonus-b", "company_id": b, "project_id": "project-b",
                "technician_name": "Admin B", "technician_name_lc": "admin b", "amount": 10,
                "project_date": "2026-10-01",
            }],
            "notifications": [{
                "id": "notification-b", "company_id": b, "user_id": "admin-b",
                "title": "Secret B", "is_read": False,
            }],
            "prospects": [{
                "id": "prospect-b", "company_id": b, "name": "Prospect B",
                "source": "manuel", "status": "nouveau", "assigned_to": "Admin B",
            }],
            "absences": [{"id": "absence-b", "company_id": b, "person_name": "Admin B"}],
            "reinterventions": [{
                "id": "reintervention-b", "company_id": b, "client_id": "client-b",
                "scheduled_date": "2026-10-20", "status": "a_faire", "photos": [],
            }],
            "off_days": [{"id": "offday-b", "company_id": b, "date": "2026-10-20", "scope": "company"}],
            "events": [{
                "id": "event-b", "company_id": b, "title": "Event B", "date": "2026-10-20",
                "all_company": True, "participants": ["admin-b"],
            }],
            "stock": [{
                "id": "stock-b", "company_id": b, "product_key": "secret-b",
                "product_name": "Secret B", "stock_disponible": 5, "commande_en_cours": 2,
                "holders": [{"user_id": "admin-b", "name": "Admin B", "qty": 1}],
            }],
            "payment_transactions": [{
                "session_id": "session-b", "company_id": b, "user_id": "admin-b",
                "payment_status": "paid", "status": "completed",
            }],
            "audit_log": [{"id": "audit-b", "company_id": b, "action": "secret"}],
        }
        for collection, docs in collections.items():
            run(self.db[collection].insert_many(docs))

    def assert_hidden(self, response, *, statuses=(403, 404)):
        self.assertIn(response.status_code, statuses, response.text)

    def test_cross_company_client_sale_and_project_ids_are_hidden(self):
        h = self.headers["admin-a"]
        calls = [
            ("put", "/api/clients/client-b", {"name": "stolen"}),
            ("delete", "/api/clients/client-b", None),
            ("get", "/api/clients/client-b/notes", None),
            ("post", "/api/clients/client-b/notes", {"text": "stolen"}),
            ("put", "/api/sales/sale-b", {"notes": "stolen"}),
            ("delete", "/api/sales/sale-b", None),
            ("get", "/api/projects/project-b", None),
            ("put", "/api/projects/project-b", {"notes": "stolen"}),
            ("delete", "/api/projects/project-b", None),
            ("post", "/api/projects/project-b/restore", None),
            ("post", "/api/projects/project-b/confirm", None),
            ("get", "/api/projects/project-b/notes", None),
            ("put", "/api/projects/project-b/notes/Admin%20B", {"note": "stolen"}),
            ("delete", "/api/projects/project-b/notes/Admin%20B", None),
            ("post", "/api/sales/sale-b/bind-commercial", {"slot": "commercial", "user_id": "admin-a"}),
            ("put", "/api/prospection/sale-b", {"prospecteur_commission": 999}),
        ]
        for method, path, payload in calls:
            with self.subTest(method=method, path=path):
                response = getattr(self.client, method)(path, headers=h, json=payload) if payload is not None else getattr(self.client, method)(path, headers=h)
                self.assert_hidden(response)
        self.assertEqual(run(self.db.clients.find_one({"id": "client-b"}))["name"], "Client B")
        self.assertEqual(run(self.db.sales.find_one({"id": "sale-b"}))["amount"], 100)

    def test_cross_company_administration_ids_are_hidden(self):
        h = self.headers["admin-a"]
        calls = [
            ("put", "/api/team/team-b", {"name": "stolen"}),
            ("delete", "/api/team/team-b", None),
            ("put", "/api/bonuses/bonus-b", {"amount": 999}),
            ("delete", "/api/bonuses/bonus-b", None),
            ("put", "/api/project-bonuses/project-bonus-b", {"amount": 999}),
            ("delete", "/api/project-bonuses/project-bonus-b", None),
            ("get", "/api/users/admin-b/permissions", None),
            ("put", "/api/users/admin-b/permissions", {"permissions": {"users": {"manage": True}}}),
            ("put", "/api/users/admin-b", {"name": "stolen"}),
            ("delete", "/api/users/admin-b", None),
            ("delete", "/api/ai/corrections/correction-b", None),
            ("patch", "/api/ai/memory/memory-b", {"content": "stolen"}),
            ("delete", "/api/ai/memory/memory-b", None),
        ]
        for method, path, payload in calls:
            with self.subTest(method=method, path=path):
                response = getattr(self.client, method)(path, headers=h, json=payload) if payload is not None else getattr(self.client, method)(path, headers=h)
                self.assert_hidden(response)
        self.assertIsNotNone(run(self.db.users.find_one({"id": "admin-b", "company_id": "company-b"})))

    def test_cross_company_planning_and_stock_ids_are_hidden(self):
        h = self.headers["admin-a"]
        calls = [
            ("put", "/api/prospects/prospect-b", {"notes": "stolen"}),
            ("delete", "/api/prospects/prospect-b", None),
            ("post", "/api/prospects/prospect-b/convert", None),
            ("delete", "/api/absences/absence-b", None),
            ("put", "/api/reinterventions/reintervention-b", {"note": "stolen"}),
            ("delete", "/api/reinterventions/reintervention-b", None),
            ("delete", "/api/off-days/offday-b", None),
            ("put", "/api/events/event-b", {"title": "stolen"}),
            ("delete", "/api/events/event-b", None),
            ("put", "/api/stock/stock-b/rename", {"product_name": "stolen"}),
            ("put", "/api/stock/stock-b/override", {"field": "besoin", "value": 999}),
            ("delete", "/api/stock/stock-b/override/besoin", None),
            ("post", "/api/stock/stock-b/receive", {"quantity": 1}),
            ("delete", "/api/stock/stock-b", None),
            ("get", "/api/stock/stock-b/holders", None),
            ("post", "/api/stock/stock-b/holder", {"user_id": "admin-a", "name": "Admin A", "quantity": 1}),
            ("post", "/api/stock/stock-b/transfer", {"from_user_id": None, "to_user_id": "admin-a", "quantity": 1}),
        ]
        for method, path, payload in calls:
            with self.subTest(method=method, path=path):
                response = getattr(self.client, method)(path, headers=h, json=payload) if payload is not None else getattr(self.client, method)(path, headers=h)
                self.assert_hidden(response)
        self.assertEqual(run(self.db.stock.find_one({"id": "stock-b"}))["product_name"], "Secret B")

    def test_lists_never_mix_companies(self):
        h = self.headers["admin-a"]
        endpoints_and_markers = [
            ("/api/clients", "client-b"),
            ("/api/sales", "sale-b"),
            ("/api/projects", "project-b"),
            ("/api/team", "team-b"),
            ("/api/bonuses", "bonus-b"),
            ("/api/project-bonuses/monthly?month=2026-10", "project-bonus-b"),
            ("/api/users", "admin-b@example.invalid"),
            ("/api/ai/corrections", "correction-b"),
            ("/api/ai/memory", "memory-b"),
            ("/api/prospects", "prospect-b"),
            ("/api/absences", "absence-b"),
            ("/api/reinterventions", "reintervention-b"),
            ("/api/off-days", "offday-b"),
            ("/api/events", "event-b"),
            ("/api/stock", "stock-b"),
            ("/api/audit", "audit-b"),
        ]
        for path, marker in endpoints_and_markers:
            with self.subTest(path=path):
                response = self.client.get(path, headers=h)
                self.assertEqual(response.status_code, 200, response.text)
                self.assertNotIn(marker, response.text)

    def test_notification_and_payment_records_require_the_same_user(self):
        h = self.headers["admin-a"]
        self.assert_hidden(self.client.put("/api/notifications/notification-b/read", headers=h))
        self.assert_hidden(self.client.delete("/api/notifications/notification-b", headers=h))
        self.assert_hidden(self.client.get("/api/payments/status/session-b", headers=h))
        self.assertFalse(run(self.db.notifications.find_one({"id": "notification-b"}))["is_read"])

    def test_commercial_cannot_restore_forged_sale_write_permissions(self):
        forged = server.get_default_permissions("commercial")
        forged["sales"].update({"create": True, "edit": True, "delete": True, "view": "all"})
        run(self.db.users.update_one({"id": "commercial-a"}, {"$set": {"permissions": forged}}))
        h = self.headers["commercial-a"]
        valid_sale = {
            "client": {"name": "Client syntaxiquement valide"},
            "service": "Service",
            "amount": 100,
            "sale_date": "2026-10-19",
        }
        self.assertEqual(self.client.post("/api/sales", headers=h, json=valid_sale).status_code, 403)
        self.assertEqual(self.client.put("/api/sales/sale-b", headers=h, json={"notes": "x"}).status_code, 403)
        self.assertEqual(self.client.delete("/api/sales/sale-b", headers=h).status_code, 403)

    def test_technician_cannot_open_administration_surfaces(self):
        h = self.headers["tech-a"]
        for path in ("/api/users", "/api/audit"):
            with self.subTest(path=path):
                self.assertEqual(self.client.get(path, headers=h).status_code, 403)
        self.assertEqual(self.client.get("/api/bonuses", headers=h).json(), [])
        team = self.client.get("/api/team", headers=h)
        self.assertEqual(team.status_code, 200)
        self.assertNotIn("@example.invalid", team.text)

    def test_suspended_account_is_limited_to_auth_and_billing(self):
        run(self.db.users.update_one({"id": "admin-a"}, {"$set": {"subscription_status": "suspended"}}))
        h = self.headers["admin-a"]
        self.assertEqual(self.client.get("/api/auth/me", headers=h).status_code, 200)
        self.assertEqual(self.client.get("/api/subscription/me", headers=h).status_code, 200)
        self.assertEqual(self.client.get("/api/clients", headers=h).status_code, 402)

    def test_super_admin_cannot_enter_business_routes(self):
        h = self.headers["super"]
        for path in ("/api/clients", "/api/sales", "/api/projects", "/api/stock"):
            with self.subTest(path=path):
                self.assertEqual(self.client.get(path, headers=h).status_code, 403)

    def test_user_owned_dashboard_configuration_is_isolated(self):
        run(self.db.user_prefs.insert_one({
            "user_id": "admin-b", "company_id": "company-b", "kind": "dashboard",
            "order": ["alerts"], "hidden": ["ca_hero"], "sizes": {"alerts": 12},
        }))
        h = self.headers["admin-a"]
        response = self.client.get("/api/me/dashboard-config", headers=h)
        self.assertEqual(response.status_code, 200, response.text)
        self.assertNotEqual(response.json().get("order"), ["alerts"])
        self.client.put("/api/me/dashboard-config", headers=h, json={"order": ["events"], "hidden": [], "sizes": {}})
        pref_b = run(self.db.user_prefs.find_one({"user_id": "admin-b", "company_id": "company-b"}))
        self.assertEqual(pref_b["order"], ["alerts"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
