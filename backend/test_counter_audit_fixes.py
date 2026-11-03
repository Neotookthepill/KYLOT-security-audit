"""Regression tests for the P1 findings of the independent counter-audit.

These tests use a disposable Mongo-compatible store, like the rest of the
in-process server suite. They do not replace a real MongoDB/concurrency test.
"""

import asyncio
import os
import unittest

os.environ.update({
    "ENVIRONMENT": "production",
    "MONGO_URL": "mongodb://127.0.0.1:27017",
    "DB_NAME": "kylot_counter_audit_test",
    "JWT_SECRET": "counter-audit-test-key-9f4b7c2e8a1d6f3b",
    "FRONTEND_URL": "https://app.example.invalid",
    "CORS_ORIGINS": "https://app.example.invalid",
    "ALLOW_PUBLIC_REGISTRATION": "false",
    "ALLOW_DEMO_DATA": "false",
    "ALLOW_TOKEN_RESPONSE": "false",
    "RUN_STARTUP_MIGRATIONS": "false",
    "EXPOSE_API_DOCS": "false",
    "COOKIE_SECURE": "true",
    "COOKIE_SAMESITE": "lax",
    "ADMIN_EMAIL": "admin@example.com",
    "ADMIN_PASSWORD": "V7!mQ2#pL9$xR4@t",
})

from fastapi.testclient import TestClient
from mongomock_motor import AsyncMongoMockClient

from backend import server
from backend.preflight import validate_config


def run(coro):
    return asyncio.run(coro)


PNG_1X1 = (
    "data:image/png;base64,"
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAACklEQVR4nGNgAAACAAEA"
    "//8DAAAGAAVXv6vUAAAAAElFTkSuQmCC"
)


class CounterAuditRegressionTests(unittest.TestCase):
    def setUp(self):
        self.mongo = AsyncMongoMockClient()
        self.db = self.mongo["kylot_counter_audit_test"]
        server.db = self.db
        server.client = self.mongo
        self.client = TestClient(server.app)
        self.company = "company-a"
        self.admin = self._user("admin", "admin@example.com", "Admin", "admin")
        self.commercial_a = self._user("commercial-a", "a@example.com", "Commercial A", "commercial")
        self.commercial_b = self._user("commercial-b", "b@example.com", "Commercial B", "commercial")
        self.tech = self._user("tech", "tech@example.com", "Tech", "technicien")
        self.comptable = self._user("compta", "compta@example.com", "Compta", "comptable")
        run(self.db.users.insert_many([
            self.admin, self.commercial_a, self.commercial_b, self.tech, self.comptable,
        ]))
        self.headers = {
            "admin": self._headers(self.admin),
            "commercial-a": self._headers(self.commercial_a),
            "commercial-b": self._headers(self.commercial_b),
            "tech": self._headers(self.tech),
            "compta": self._headers(self.comptable),
        }

    def tearDown(self):
        self.client.close()
        self.mongo.close()

    def _user(self, uid, email, name, role):
        return {
            "id": uid,
            "email": email,
            "name": name,
            "role": role,
            "company_id": self.company,
            "permissions": server.get_default_permissions(role),
        }

    @staticmethod
    def _headers(user):
        return {"Authorization": f"Bearer {server.create_access_token(user['id'], user['email'])}"}

    def test_clients_pagination_is_bounded_and_reports_total(self):
        run(self.db.clients.insert_many([
            {"id": f"c-{i}", "company_id": self.company, "name": f"Client {i}",
             "created_by": self.admin["id"], "created_at": f"2026-10-0{i+1}T00:00:00Z"}
            for i in range(3)
        ]))
        first = self.client.get(
            "/api/clients?limit=2&offset=0", headers=self.headers["admin"]
        )
        self.assertEqual(first.status_code, 200, first.text)
        self.assertEqual(len(first.json()), 2)
        self.assertEqual(first.headers.get("x-total-count"), "3")
        second = self.client.get(
            "/api/clients?limit=2&offset=2", headers=self.headers["admin"]
        )
        self.assertEqual(second.status_code, 200, second.text)
        self.assertEqual(len(second.json()), 1)

    def test_sales_status_order_is_applied_before_pagination(self):
        run(self.db.sales.insert_many([
            {"id": "s-1", "company_id": self.company, "sale_date": "2026-10-01",
             "amount": 100, "status": "annule", "commercial": "Alice"},
            {"id": "s-2", "company_id": self.company, "sale_date": "2026-10-02",
             "amount": 200, "status": "en_cours", "commercial": "Alice"},
            {"id": "s-3", "company_id": self.company, "sale_date": "2026-10-03",
             "amount": 300, "status": "termine", "commercial": "Alice"},
        ]))
        response = self.client.get(
            "/api/sales?status_order=termine%7Cen_cours%7Cannule&limit=10",
            headers=self.headers["admin"],
        )
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual([s["id"] for s in response.json()], ["s-3", "s-2", "s-1"])

    def test_sales_summary_aggregates_deals_and_excludes_cancelled(self):
        run(self.db.sales.insert_many([
            {"id": "s-de", "company_id": self.company, "sale_date": "2026-10-01",
             "amount": 1000, "status": "en_cours", "commercial": "Alice",
             "commercial_2": "Bob", "is_de": True, "source": "R1",
             "payment_method": "financement"},
            {"id": "s-cash", "company_id": self.company, "sale_date": "2026-10-02",
             "amount": 500, "status": "argent_recupere", "commercial": "Alice",
             "source": "CQ", "payment_method": "cheque"},
            {"id": "s-cancel", "company_id": self.company, "sale_date": "2026-10-03",
             "amount": 999, "status": "annule", "commercial": "Alice"},
        ]))
        response = self.client.get(
            "/api/sales/summary?from_date=2026-10-01&to_date=2026-10-31",
            headers=self.headers["admin"],
        )
        self.assertEqual(response.status_code, 200, response.text)
        data = response.json()
        self.assertEqual(data["count"], 3)
        self.assertEqual(data["total"], 1500)
        by_name = {row["name"]: row for row in data["by_commercial"]}
        self.assertEqual(by_name["Alice"]["ca"], 1000)
        self.assertEqual(by_name["Alice"]["count"], 2)
        self.assertEqual(by_name["Bob"]["ca"], 500)

    def test_client_search_category_filter_and_counts(self):
        run(self.db.clients.insert_many([
            {"id": "c-a", "company_id": self.company, "name": "Alice Lyon",
             "city": "Lyon", "created_by": self.admin["id"],
             "categories": [{"category_key": "vip", "sub_status_key": "gold"}]},
            {"id": "c-b", "company_id": self.company, "name": "Bob Paris",
             "city": "Paris", "created_by": self.admin["id"],
             "categories": [{"category_key": "vip"}]},
            {"id": "c-c", "company_id": self.company, "name": "Alice Nice",
             "city": "Nice", "created_by": self.admin["id"], "categories": []},
        ]))
        search = self.client.get(
            "/api/clients?q=Alice&limit=10", headers=self.headers["admin"]
        )
        self.assertEqual(search.status_code, 200, search.text)
        self.assertEqual({c["id"] for c in search.json()}, {"c-a", "c-c"})
        self.assertEqual(search.headers.get("x-total-count"), "2")
        filtered = self.client.get(
            "/api/clients?category_key=vip&sub_status_key=gold&limit=10",
            headers=self.headers["admin"],
        )
        self.assertEqual(filtered.status_code, 200, filtered.text)
        self.assertEqual([c["id"] for c in filtered.json()], ["c-a"])
        counts = self.client.get(
            "/api/clients/category-counts", headers=self.headers["admin"]
        )
        self.assertEqual(counts.status_code, 200, counts.text)
        self.assertEqual(counts.json()["all"], 3)
        self.assertEqual(counts.json()["categories"]["vip"], 2)

    def test_audit_pagination_applies_offset_and_reports_total(self):
        run(self.db.audit_log.insert_many([
            {"id": f"a-{i}", "company_id": self.company, "user_id": self.admin["id"],
             "user_name": "Admin", "user_role": "admin", "action": "update",
             "resource": "client", "resource_id": f"c-{i}", "at": f"2026-10-0{i+1}T00:00:00Z"}
            for i in range(3)
        ]))
        first = self.client.get(
            "/api/audit?limit=2&offset=0", headers=self.headers["admin"]
        )
        self.assertEqual(first.status_code, 200, first.text)
        self.assertEqual(len(first.json()), 2)
        self.assertEqual(first.headers.get("x-total-count"), "3")
        second = self.client.get(
            "/api/audit?limit=2&offset=2", headers=self.headers["admin"]
        )
        self.assertEqual(second.status_code, 200, second.text)
        self.assertEqual(len(second.json()), 1)

    def test_login_rejects_special_use_email_instead_of_creating_unreachable_account(self):
        response = self.client.post("/api/auth/login", json={
            "email": "admin@example.invalid", "password": "fictitious-password",
        })
        self.assertEqual(response.status_code, 422, response.text)

    def test_sale_double_submit_with_same_request_id_is_idempotent(self):
        payload = {
            "client": {"name": "Client idempotent"},
            "service": "Prestation",
            "amount": 1000,
            "sale_date": "2026-10-01",
            "status": "en_cours",
            "commercial": "Admin",
            "client_request_id": "req-12345678",
        }
        first = self.client.post("/api/sales", headers=self.headers["admin"], json=payload)
        second = self.client.post("/api/sales", headers=self.headers["admin"], json=payload)
        self.assertEqual(first.status_code, 200, first.text)
        self.assertEqual(second.status_code, 200, second.text)
        self.assertEqual(first.json()["id"], second.json()["id"])
        self.assertEqual(run(self.db.sales.count_documents({})), 1)
        self.assertEqual(run(self.db.projects.count_documents({})), 1)

    def test_commercial_cannot_read_personal_off_days_team_targets_or_bonus_rules(self):
        run(self.db.team_members.insert_one({
            "id": "tm-other", "company_id": self.company, "name": "Other",
            "type": "commercial", "email": "other@example.com", "objectif": 90000,
        }))
        run(self.db.off_days.insert_one({
            "id": "off-personal", "company_id": self.company, "date": "2026-11-10",
            "scope": "person", "person_names": ["Tech"], "reason": "Arrêt maladie",
        }))
        team = self.client.get("/api/team", headers=self.headers["commercial-a"]).json()
        self.assertTrue(all("email" not in row and "objectif" not in row for row in team))
        off_days = self.client.get("/api/off-days?month=2026-11", headers=self.headers["commercial-a"]).json()
        self.assertEqual(off_days, [])
        settings = self.client.get("/api/settings", headers=self.headers["commercial-a"]).json()
        self.assertEqual(settings["prospect_mgr_rate_below"], 0)
        self.assertEqual(settings["prospect_mgr_bonuses"], [])

    def test_legacy_team_scope_is_normalized_to_own(self):
        permissions = server.get_default_permissions("commercial")
        permissions["sales"]["view"] = "team"
        run(self.db.users.update_one({"id": "commercial-a"}, {"$set": {"permissions": permissions}}))
        run(self.db.sales.insert_one({
            "id": "sale-b", "company_id": self.company, "client_id": "client-b",
            "commercial": "Commercial B", "commercial_user_id": "commercial-b",
            "amount": 100, "sale_date": "2026-10-01", "status": "en_cours",
        }))
        response = self.client.get("/api/sales", headers=self.headers["commercial-a"])
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json(), [])

    def test_new_password_hashes_are_not_truncated_at_72_bytes(self):
        password = "é" * 40
        digest = server.hash_password(password)
        self.assertTrue(digest.startswith("sha256$"))
        self.assertTrue(server.verify_password(password, digest))
        self.assertFalse(server.verify_password("é" * 36 + "zz", digest))

    def test_client_import_cannot_update_a_colleagues_client(self):
        run(self.db.clients.insert_one({
            "id": "client-a", "company_id": self.company, "name": "Client A",
            "phone": "0611223344", "email": "client-a@example.com",
            "address": "1 rue A", "notes": "secret A", "created_by": self.commercial_a["id"],
        }))
        response = self.client.post("/api/clients/import/execute", headers=self.headers["commercial-b"], json={
            "mapping": {"0": "name", "1": "phone", "2": "notes"},
            "rows": [["Intrusion", "0611223344", "modifié par B"]],
            "duplicate_strategy": "update",
        })
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["updated_count"], 0)
        self.assertEqual(response.json()["skipped"][0]["reason"], "doublon hors périmètre")
        stored = run(self.db.clients.find_one({"id": "client-a"}))
        self.assertEqual(stored["notes"], "secret A")

    def test_pdf_import_does_not_disclose_a_colleagues_client(self):
        run(self.db.clients.insert_one({
            "id": "client-a", "company_id": self.company, "name": "Client A",
            "phone": "0611223344", "email": "client-a@example.com",
            "address": "1 rue A", "notes": "secret A", "created_by": self.commercial_a["id"],
        }))
        response = self.client.post("/api/clients/import/pdf/create", headers=self.headers["commercial-b"], json={
            "name": "Intrusion", "phone": "0611223344", "duplicate_strategy": "update",
        })
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["action"], "skipped")
        self.assertNotIn("existing", response.json())
        stored = run(self.db.clients.find_one({"id": "client-a"}))
        self.assertEqual(stored["name"], "Client A")

    def test_stock_drilldown_respects_project_scope(self):
        run(self.db.stock.insert_one({
            "id": "stock-cable", "company_id": self.company, "product_key": "cable",
            "product_name": "Cable", "stock_disponible": 10, "holders": [],
        }))
        run(self.db.clients.insert_one({"id": "client-other", "company_id": self.company, "name": "Client secret"}))
        run(self.db.sales.insert_one({
            "id": "sale-other", "company_id": self.company, "client_id": "client-other",
            "commercial": "Other", "amount": 12345, "status": "en_cours",
            "prestations": [{"name": "Cable", "quantity": 5}],
        }))
        run(self.db.projects.insert_one({
            "id": "project-other", "company_id": self.company, "client_id": "client-other",
            "sale_id": "sale-other", "assigned_to": ["Other Tech"], "status": "en_cours",
            "prestations": [{"name": "Cable", "quantity": 5}],
        }))
        response = self.client.get("/api/stock/product/cable/projects", headers=self.headers["tech"])
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["projects"], [])

    def test_completion_requires_project_edit_and_photo_add(self):
        permissions = server.get_default_permissions("technicien")
        permissions["projects"] = {"view": "none", "create": False, "edit": False, "delete": False}
        permissions["photos"] = {"view": False, "add": False}
        run(self.db.users.update_one({"id": "tech"}, {"$set": {"permissions": permissions}}))
        run(self.db.projects.insert_one({
            "id": "project-tech", "company_id": self.company, "client_id": "client",
            "sale_id": "sale", "assigned_to": ["Tech"], "status": "en_cours",
            "scheduled_date": "2026-10-01", "photos": [],
        }))
        response = self.client.post("/api/projects/project-tech/complete", headers=self.headers["tech"], json={
            "photos": [PNG_1X1],
        })
        self.assertEqual(response.status_code, 403, response.text)
        stored = run(self.db.projects.find_one({"id": "project-tech"}))
        self.assertEqual(stored["status"], "en_cours")

    def test_note_requires_project_edit(self):
        permissions = server.get_default_permissions("technicien")
        permissions["projects"]["edit"] = False
        run(self.db.users.update_one({"id": "tech"}, {"$set": {"permissions": permissions}}))
        run(self.db.projects.insert_one({
            "id": "project-note", "company_id": self.company, "client_id": "client",
            "sale_id": "sale", "assigned_to": ["Tech"], "status": "en_cours",
            "scheduled_date": "2026-10-01", "photos": [],
        }))
        response = self.client.put(
            "/api/projects/project-note/notes/Tech", headers=self.headers["tech"], json={"note": "test"}
        )
        self.assertEqual(response.status_code, 403, response.text)

    def test_technician_without_stock_permissions_cannot_create_stock(self):
        permissions = server.get_default_permissions("technicien")
        permissions["stock"] = {
            "view": False, "edit": False, "view_own": False,
            "view_others": False, "view_company": False,
        }
        run(self.db.users.update_one({"id": "tech"}, {"$set": {"permissions": permissions}}))
        response = self.client.post(
            "/api/stock/tech-create-and-hold",
            headers=self.headers["tech"],
            json={"product_name": "Produit interdit", "qty": 5},
        )
        self.assertEqual(response.status_code, 403, response.text)
        self.assertEqual(run(self.db.stock.count_documents({})), 0)

    def test_accountant_cannot_adjust_a_holder(self):
        run(self.db.stock.insert_one({
            "id": "stock-cable", "company_id": self.company, "product_key": "cable",
            "product_name": "Cable", "stock_disponible": 10, "holders": [],
        }))
        response = self.client.post(
            "/api/stock/stock-cable/holder-adjust",
            headers=self.headers["compta"],
            json={"delta": 7},
        )
        self.assertEqual(response.status_code, 403, response.text)

    def test_bonus_progress_is_hidden_from_technicians(self):
        run(self.db.team_members.insert_many([
            {"id": "tm-a", "company_id": self.company, "name": "Alice", "type": "commercial"},
            {"id": "tm-b", "company_id": self.company, "name": "Bob", "type": "commercial"},
        ]))
        run(self.db.bonuses.insert_one({
            "id": "bonus-secret", "company_id": self.company, "name": "Prime secrète",
            "ca_threshold": 10000, "amount": 500, "period": "month",
            "commerciaux": ["*"], "active": True,
        }))
        response = self.client.get("/api/bonuses/progress", headers=self.headers["tech"])
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json(), [])

    def test_exact_homonyms_do_not_share_prospects_sales_or_overtime(self):
        # Deux comptes strictement homonymes, créés directement en base comme
        # pourraient l'être des données historiques.
        for uid, email in (("h1", "h1@example.com"), ("h2", "h2@example.com")):
            run(self.db.users.insert_one({
                "id": uid, "email": email, "name": "Jean Dupont",
                "role": "commercial", "company_id": self.company,
                "permissions": server.get_default_permissions("commercial"),
            }))
        run(self.db.prospects.insert_one({
            "id": "prospect-h1", "company_id": self.company, "name": "Prospect confidentiel",
            "assigned_to": "Jean Dupont", "assigned_to_id": "h1", "created_by": "h1",
        }))
        run(self.db.sales.insert_one({
            "id": "sale-h1", "company_id": self.company, "client_id": "client-h1",
            "commercial": "Jean Dupont", "commercial_user_id": None,
            "amount": 100, "sale_date": "2026-10-01", "status": "en_cours",
        }))
        run(self.db.overtime.insert_one({
            "id": "ot-h1", "company_id": self.company, "technician_name": "Jean Dupont",
            "technician_user_id": "h1", "date": "2026-10-01", "hours": 2, "status": "pending",
        }))
        h1 = {"Authorization": f"Bearer {server.create_access_token('h1', 'h1@example.com')}"}
        h2 = {"Authorization": f"Bearer {server.create_access_token('h2', 'h2@example.com')}"}
        self.assertEqual(len(self.client.get("/api/prospects", headers=h1).json()), 1)
        self.assertEqual(self.client.get("/api/prospects", headers=h2).json(), [])
        self.assertEqual(self.client.get("/api/sales", headers=h2).json(), [])
        # Un commercial n'a pas overtime.view par défaut : le test vérifie
        # surtout que le prospect et la vente ne fuitent pas par homonymie.
        self.assertEqual(self.client.get("/api/overtime?month=2026-10", headers=h2).status_code, 403)

    def test_company_subscription_change_applies_to_every_member(self):
        second_admin = self._user("admin-2", "admin2@example.com", "Admin 2", "admin")
        outsider = {
            "id": "outsider", "email": "out@example.com", "name": "Out",
            "role": "admin", "company_id": "company-b",
            "permissions": server.get_default_permissions("admin"),
        }
        run(self.db.users.insert_many([second_admin, outsider]))
        run(self.db.payment_transactions.insert_one({
            "session_id": "cs-refund", "user_id": self.admin["id"], "company_id": self.company,
            "stripe_payment_intent_id": "pi-refund", "status": "completed", "payment_status": "paid",
        }))
        run(server._set_payment_intent_status("pi-refund", "refunded", suspend=True))
        for uid in ("admin", "admin-2", "commercial-a"):
            stored = run(self.db.users.find_one({"id": uid}))
            self.assertEqual(stored["subscription_status"], "suspended")
        self.assertIsNone(run(self.db.users.find_one({"id": "outsider"})).get("subscription_status"))

    def test_migration_backfills_every_tenant_collection(self):
        run(self.db.client_notes.insert_one({"id": "note-legacy", "text": "legacy"}))
        run(self.db.stock.insert_one({"id": "stock-legacy", "product_name": "Legacy"}))
        run(self.db.events.insert_one({"id": "event-legacy", "title": "Legacy"}))
        run(server.migrate_multi_tenant())
        for collection, doc_id in (
            ("client_notes", "note-legacy"),
            ("stock", "stock-legacy"),
            ("events", "event-legacy"),
        ):
            stored = run(self.db[collection].find_one({"id": doc_id}))
            self.assertEqual(stored["company_id"], server.DEFAULT_COMPANY_ID)


class PreflightCounterAuditTests(unittest.TestCase):
    def _valid_env(self):
        return {
            "ENVIRONMENT": "production",
            "APP_VERSION": "0123456789abcdef",
            "MONGO_URL": "mongodb://database.internal:27017",
            "DB_NAME": "kylot",
            "JWT_SECRET": "Q7mZ2pL9vX4cR8sT1nB6kH3dF5gJ0wAe",
            "FRONTEND_URL": "https://app.example.invalid",
            "CORS_ORIGINS": "https://app.example.invalid",
            "ALLOW_PUBLIC_REGISTRATION": "false",
            "ALLOW_DEMO_DATA": "false",
            "ALLOW_TOKEN_RESPONSE": "false",
            "RUN_STARTUP_MIGRATIONS": "false",
            "EXPOSE_API_DOCS": "false",
            "ALLOW_EXTERNAL_GEOCODING": "false",
            "COOKIE_SECURE": "true",
            "COOKIE_SAMESITE": "lax",
            "TRUST_PROXY_HEADERS": "false",
            "ADMIN_EMAIL": "admin@example.com",
            "ADMIN_PASSWORD": "V7!mQ2#pL9$xR4@t",
            "SUPER_ADMIN_EMAIL": "owner@example.com",
            "SUPER_ADMIN_PASSWORD": "K3@nW8!zB5$cF1#q",
            "EMERGENT_LLM_KEY": "configured",
            "EMERGENT_EMAIL_KEY": "configured",
            "STRIPE_SECRET_KEY": "configured",
            "STRIPE_WEBHOOK_SECRET": "configured",
            "STRIPE_RETURN_ORIGINS": "https://app.example.invalid",
            "WEBHOOK_CRON_SECRET": "H4$kP9!mR2@vT7#xL6&nQ1Z8",
        }

    def test_rejects_special_use_admin_email(self):
        env = self._valid_env()
        env["ADMIN_EMAIL"] = "admin@example.invalid"
        result = validate_config(env)
        self.assertTrue(any("ADMIN_EMAIL" in error for error in result.errors))

    def test_requires_explicit_environment_and_rejects_repeated_secret(self):
        env = self._valid_env()
        env.pop("ENVIRONMENT")
        result = validate_config(env)
        self.assertTrue(any("ENVIRONMENT" in error for error in result.errors))
        env = self._valid_env()
        env["JWT_SECRET"] = "a" * 40
        result = validate_config(env)
        self.assertTrue(any("JWT_SECRET" in error for error in result.errors))


if __name__ == "__main__":
    unittest.main()
