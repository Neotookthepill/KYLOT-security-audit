"""Adversarial security checks for KYLOT.

This suite is intentionally kept outside the default pytest discovery paths.
Each check describes the secure behaviour expected before production. A failing
check is an audit finding, not a flaky test to ignore.
"""

from __future__ import annotations

import asyncio
import ast
import os
import re
import unittest
from pathlib import Path
from unittest.mock import patch


os.environ.update({
    "ENVIRONMENT": "production",
    "MONGO_URL": "mongodb://127.0.0.1:27017",
    "DB_NAME": "kylot_adversarial_test",
    "JWT_SECRET": "adversarial-test-secret-at-least-32-characters",
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


ROOT = Path(__file__).resolve().parents[1]
SERVER_SOURCE = (ROOT / "backend/server.py").read_text(encoding="utf-8")


def run(coro):
    return asyncio.run(coro)


class IdentityAndAuthorizationChecks(unittest.TestCase):
    def setUp(self):
        self.mongo = AsyncMongoMockClient()
        self.db = self.mongo["kylot_adversarial_test"]
        server.db = self.db
        server.client = self.mongo
        self.client = TestClient(server.app)
        self.admin = {
            "id": "admin-a",
            "email": "admin-a@example.invalid",
            "name": "Admin A",
            "password_hash": server.hash_password("correct-password-admin-a"),
            "role": "admin",
            "company_id": "company-a",
            "permissions": server.get_default_permissions("admin"),
        }
        self.jean = {
            "id": "tech-jean-dupont",
            "email": "jean.dupont@example.invalid",
            "name": "Jean Dupont",
            "password_hash": server.hash_password("correct-password-jean-dupont"),
            "role": "technicien",
            "company_id": "company-a",
            "permissions": server.get_default_permissions("technicien"),
        }
        run(self.db.users.insert_many([self.admin, self.jean]))
        self.admin_headers = {
            "Authorization": f"Bearer {server.create_access_token(self.admin['id'], self.admin['email'])}"
        }

    def tearDown(self):
        self.client.close()
        self.mongo.close()

    def test_distinct_people_with_same_first_name_never_match(self):
        self.assertFalse(server._fuzzy_name_match("Jean Dupont", "Jean Martin"))

    def test_distinct_people_with_same_surname_never_match(self):
        self.assertFalse(server._fuzzy_name_match("Alice Martin", "Bob Martin"))

    def test_identity_normalization_is_accent_and_whitespace_insensitive(self):
        self.assertEqual(server._norm_name("  Théo   Dudal "), "theo dudal")

    def test_legacy_sale_scope_never_authorizes_by_first_name_only(self):
        query = server._own_sales_filter({"id": "jean-1", "name": "Jean Dupont"})
        patterns = [
            condition["commercial"]["$regex"].pattern
            for branch in query["$or"]
            for condition in branch.get("$and", [])
            if "commercial" in condition and "$regex" in condition["commercial"]
        ]
        self.assertNotIn(r"^\s*(?:jean|Jean)\b", patterns)

    def test_overtime_eligibility_cannot_be_inherited_from_a_namesake(self):
        run(self.db.team_members.insert_one({
            "id": "tm-jean-martin",
            "company_id": "company-a",
            "type": "technicien",
            "name": "Jean Martin",
            "email": "jean.martin@example.invalid",
            "overtime_enabled": True,
        }))
        user = dict(self.jean)
        run(server._apply_overtime_eligibility_gate(user))
        self.assertFalse(user["permissions"]["overtime"]["declare"])

    def test_namesake_cannot_open_another_technicians_project_by_id(self):
        run(self.db.clients.insert_one({
            "id": "client-martin", "company_id": "company-a", "name": "Client Martin",
        }))
        run(self.db.sales.insert_one({
            "id": "sale-martin", "company_id": "company-a", "client_id": "client-martin",
            "commercial": "Admin A",
        }))
        run(self.db.projects.insert_one({
            "id": "project-jean-martin", "company_id": "company-a",
            "client_id": "client-martin", "sale_id": "sale-martin",
            "assigned_to": ["Jean Martin"], "status": "en_cours", "photos": [],
        }))
        headers = {
            "Authorization": f"Bearer {server.create_access_token(self.jean['id'], self.jean['email'])}"
        }
        response = self.client.get("/api/projects/project-jean-martin", headers=headers)
        self.assertEqual(response.status_code, 404, response.text)

    def test_admin_password_reset_revokes_existing_sessions(self):
        old_token = server.create_access_token(self.jean["id"], self.jean["email"])
        old_headers = {"Authorization": f"Bearer {old_token}"}
        self.assertEqual(self.client.get("/api/auth/me", headers=old_headers).status_code, 200)
        changed = self.client.put(
            f"/api/users/{self.jean['id']}",
            headers=self.admin_headers,
            json={"password": "a-new-strong-password-for-jean"},
        )
        self.assertEqual(changed.status_code, 200, changed.text)
        self.assertEqual(self.client.get("/api/auth/me", headers=old_headers).status_code, 401)


class InputAndTransportChecks(unittest.TestCase):
    def test_only_expected_routes_are_public(self):
        tree = ast.parse(SERVER_SOURCE)
        public = set()
        for node in tree.body:
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            source = ast.get_source_segment(SERVER_SOURCE, node) or ""
            protected = any(name in source for name in (
                "get_current_user", "require_admin", "require_super_admin", "require_sales_access",
            ))
            if protected:
                continue
            for decorator in node.decorator_list:
                if not (isinstance(decorator, ast.Call) and isinstance(decorator.func, ast.Attribute)):
                    continue
                if decorator.func.attr not in {"get", "post", "put", "patch", "delete"} or not decorator.args:
                    continue
                try:
                    path = ast.literal_eval(decorator.args[0])
                except Exception:
                    continue
                public.add((decorator.func.attr.upper(), path))
        expected = {
            ("POST", "/auth/register"), ("POST", "/auth/login"), ("POST", "/auth/logout"),
            ("POST", "/cron/rappel-chantiers-j1"), ("POST", "/cron/bilan-mensuel"),
            ("POST", "/stripe/webhook"),
            ("GET", "/health"), ("GET", "/healthz"), ("GET", "/api/health"), ("GET", "/api/healthz"),
            ("GET", "/ready"), ("GET", "/readyz"), ("GET", "/api/ready"),
            ("GET", "/api/version"),
        }
        self.assertEqual(public, expected)

    def test_runtime_email_guard_rejects_misleading_anchor(self):
        with self.assertRaises(ValueError):
            server._assert_safe_email(
                "Votre compte",
                '<a href="https://attacker.example">https://bank.example</a>',
            )

    def test_runtime_email_guard_rejects_credential_request(self):
        with self.assertRaises(ValueError):
            server._assert_safe_email(
                "Vérification",
                "Please reply with your password so we can verify your account.",
            )

    def test_security_symbols_are_not_redefined_later(self):
        tree = ast.parse(SERVER_SOURCE)
        definitions: dict[str, list[int]] = {}
        for node in tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                definitions.setdefault(node.name, []).append(node.lineno)
        security_names = {"_norm_name", "_EmailScan", "_assert_safe_email"}
        duplicates = {name: definitions.get(name, []) for name in security_names if len(definitions.get(name, [])) > 1}
        self.assertEqual(duplicates, {})

    def test_request_size_limit_is_not_content_length_only(self):
        middleware = SERVER_SOURCE.split(
            "async def security_headers_and_request_limits", 1
        )[1].split("# --- Kubernetes", 1)[0]
        self.assertTrue(
            "request.stream()" in middleware or "receive" in middleware,
            "The application must cap streamed/chunked request bodies too",
        )

    def test_cron_idempotency_has_a_unique_database_constraint(self):
        self.assertRegex(
            SERVER_SOURCE,
            r"cron_runs\.create_index\([^\n]+unique\s*=\s*True",
        )

    def test_password_fields_are_masked_and_help_text_matches_server_policy(self):
        users = (ROOT / "frontend/src/pages/Users.jsx").read_text(encoding="utf-8")
        companies = (ROOT / "frontend/src/pages/Companies.jsx").read_text(encoding="utf-8")
        self.assertNotRegex(users, r'Input\s+type="text"[^>]+password')
        self.assertNotRegex(companies, r'Input\s+type="text"[^>]+admin_password')
        self.assertNotIn("Min. 6 caractères", users)
        self.assertNotIn("Min. 6 caractères", companies)

    def test_repository_contains_no_live_environment_credentials(self):
        forbidden = re.compile(
            r"preview\.emergentagent\.com|Admin@2026|kilianblanc0202@gmail\.com",
            re.IGNORECASE,
        )
        hits = []
        for path in list((ROOT / "tests").glob("*.py")) + list((ROOT / "backend/tests").glob("*.py")):
            text = path.read_text(encoding="utf-8", errors="ignore")
            if forbidden.search(text):
                hits.append(str(path.relative_to(ROOT)))
        self.assertEqual(hits, [], f"Potential live credentials/endpoints remain in: {hits}")

    def test_inline_image_content_matches_declared_image_type(self):
        fake_png = "data:image/png;base64,ZXZpbA=="  # bytes are the word 'evil', not a PNG
        with self.assertRaises(Exception):
            server._validated_photo_source(fake_png)

    def test_external_photo_urls_are_not_accepted_as_arbitrary_tracking_pixels(self):
        with self.assertRaises(Exception):
            server._validated_photo_source("https://tracking.attacker.invalid/pixel.png?user=123")

    def test_privileged_user_update_is_audited(self):
        update_body = SERVER_SOURCE.split("async def update_user", 1)[1].split(
            "async def delete_user", 1
        )[0]
        self.assertIn("log_audit(", update_body)

    def test_critical_queries_have_compound_tenant_indexes(self):
        required = {
            "sales": "company_id,id",
            "projects": "company_id,id",
            "project_notes": "company_id,project_id,technician_name_lc",
            "project_bonuses": "company_id,project_id,technician_name_lc",
            "payment_transactions": "company_id,session_id",
        }
        compact = re.sub(r"\s+", "", SERVER_SOURCE)
        missing = []
        for collection, fields in required.items():
            ordered = ",".join(f'(\"{field}\",1)' for field in fields.split(","))
            if f"db.{collection}.create_index([{ordered}]" not in compact:
                missing.append(f"{collection}({fields})")
        self.assertEqual(missing, [])


class ConcurrencyChecks(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.mongo = AsyncMongoMockClient()
        self.db = self.mongo["kylot_concurrency_test"]
        server.db = self.db
        server.client = self.mongo
        self.manager = {
            "id": "manager-a", "email": "manager@example.invalid", "name": "Manager A",
            "role": "admin", "company_id": "company-a",
            "permissions": server.get_default_permissions("admin"),
        }
        await self.db.users.insert_many([
            self.manager,
            {"id": "tech-a", "name": "Tech A", "email": "a@example.invalid", "company_id": "company-a", "role": "technicien"},
            {"id": "tech-b", "name": "Tech B", "email": "b@example.invalid", "company_id": "company-a", "role": "technicien"},
        ])

    async def asyncTearDown(self):
        self.mongo.close()

    async def test_two_simultaneous_stock_transfers_do_not_lose_inventory_updates(self):
        await self.db.stock.insert_one({
            "id": "stock-race", "company_id": "company-a", "product_key": "cable",
            "product_name": "Cable", "stock_disponible": 10, "holders": [],
        })
        original_find_one = self.db.stock.find_one
        arrivals = 0
        gate = asyncio.Event()

        async def synchronized_find_one(*args, **kwargs):
            nonlocal arrivals
            result = await original_find_one(*args, **kwargs)
            if args and args[0].get("id") == "stock-race":
                arrivals += 1
                if arrivals >= 2:
                    gate.set()
                await gate.wait()
            return result

        with patch.object(self.db.stock, "find_one", side_effect=synchronized_find_one):
            await asyncio.gather(
                server.transfer_stock(
                    "stock-race",
                    server.StockTransferIn(from_user_id=None, to_user_id="tech-a", quantity=5),
                    self.manager,
                ),
                server.transfer_stock(
                    "stock-race",
                    server.StockTransferIn(from_user_id=None, to_user_id="tech-b", quantity=5),
                    self.manager,
                ),
            )
        row = await self.db.stock.find_one({"id": "stock-race"})
        self.assertEqual(row["stock_disponible"], 0)
        self.assertEqual({h["user_id"]: h["qty"] for h in row["holders"]}, {"tech-a": 5, "tech-b": 5})

    async def test_simultaneous_bonus_creation_remains_unique(self):
        await self.db.projects.insert_one({
            "id": "project-race", "company_id": "company-a", "assigned_to": ["Tech A"],
            "status": "termine", "scheduled_date": "2026-10-16",
        })
        original_find_one = self.db.project_bonuses.find_one
        arrivals = 0
        gate = asyncio.Event()

        async def synchronized_find_one(*args, **kwargs):
            nonlocal arrivals
            result = await original_find_one(*args, **kwargs)
            arrivals += 1
            if arrivals >= 2:
                gate.set()
            await gate.wait()
            return result

        with patch.object(self.db.project_bonuses, "find_one", side_effect=synchronized_find_one):
            await asyncio.gather(
                server.create_project_bonus(
                    "project-race", server.ProjectBonusIn(technician_name="Tech A", amount=50), self.manager
                ),
                server.create_project_bonus(
                    "project-race", server.ProjectBonusIn(technician_name="Tech A", amount=50), self.manager
                ),
            )
        count = await self.db.project_bonuses.count_documents({
            "company_id": "company-a", "project_id": "project-race", "technician_name_lc": "tech a",
        })
        self.assertEqual(count, 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
