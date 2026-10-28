"""Independent counter-audit checks not covered by rounds 1 and 2."""

from __future__ import annotations

import asyncio
import os
import unittest
from pathlib import Path


os.environ.update({
    "ENVIRONMENT": "production",
    "MONGO_URL": "mongodb://127.0.0.1:27017",
    "DB_NAME": "kylot_adversarial_round3",
    "JWT_SECRET": "round-three-adversarial-secret-at-least-32-characters",
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
from pydantic import ValidationError

from backend import server


ROOT = Path(__file__).resolve().parents[1]
SERVER_SOURCE = (ROOT / "backend/server.py").read_text(encoding="utf-8")
AUTH_SOURCE = (ROOT / "frontend/src/contexts/AuthContext.jsx").read_text(encoding="utf-8")
API_SOURCE = (ROOT / "frontend/src/lib/api.js").read_text(encoding="utf-8")
AI_HELPER_SOURCE = (ROOT / "frontend/src/components/AIHelper.jsx").read_text(encoding="utf-8")


def run(coro):
    return asyncio.run(coro)


class CounterAuditHTTPChecks(unittest.TestCase):
    def setUp(self):
        self.mongo = AsyncMongoMockClient()
        self.db = self.mongo["kylot_adversarial_round3"]
        server.db = self.db
        server.client = self.mongo
        self.client = TestClient(server.app)
        self.admin = {
            "id": "admin-a", "email": "admin@example.com", "name": "Admin A",
            "password_hash": server.hash_password("correct-password-admin-round-three"),
            "role": "admin", "company_id": "company-a",
            "permissions": server.get_default_permissions("admin"),
        }
        commercial_permissions = server.get_default_permissions("commercial")
        commercial_permissions["clients"]["edit"] = False
        self.commercial = {
            "id": "commercial-a", "email": "commercial@example.com", "name": "Sales A",
            "password_hash": server.hash_password("correct-password-commercial-three"),
            "role": "commercial", "company_id": "company-a", "permissions": commercial_permissions,
        }
        self.tech = {
            "id": "tech-a", "email": "tech@example.com", "name": "Tech A",
            "password_hash": server.hash_password("correct-password-tech-round-three"),
            "role": "technicien", "company_id": "company-a",
            "permissions": server.get_default_permissions("technicien"),
        }
        run(self.db.users.insert_many([self.admin, self.commercial, self.tech]))
        self.admin_headers = {"Authorization": f"Bearer {server.create_access_token(self.admin['id'], self.admin['email'])}"}
        self.commercial_headers = {"Authorization": f"Bearer {server.create_access_token(self.commercial['id'], self.commercial['email'])}"}
        self.tech_headers = {"Authorization": f"Bearer {server.create_access_token(self.tech['id'], self.tech['email'])}"}

    def tearDown(self):
        self.client.close()
        self.mongo.close()

    def test_deleting_client_with_history_is_blocked_or_soft_deleted(self):
        run(self.db.clients.insert_one({"id": "client-live", "company_id": "company-a", "name": "Client Live"}))
        run(self.db.sales.insert_one({
            "id": "sale-live", "company_id": "company-a", "client_id": "client-live",
            "service": "Service", "sale_date": "2026-10-16", "status": "en_cours",
        }))
        response = self.client.delete("/api/clients/client-live", headers=self.admin_headers)
        self.assertIn(response.status_code, (400, 409), response.text)
        self.assertIsNotNone(run(self.db.clients.find_one({"id": "client-live"})))

    def test_deleting_sale_preserves_linked_project_and_photos(self):
        photo = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
        run(self.db.sales.insert_one({
            "id": "sale-history", "company_id": "company-a", "client_id": "client-history",
            "service": "Service", "sale_date": "2026-10-16", "status": "chantier_fini",
        }))
        run(self.db.projects.insert_one({
            "id": "project-history", "company_id": "company-a", "sale_id": "sale-history",
            "client_id": "client-history", "status": "termine", "photos": [photo],
        }))
        response = self.client.delete("/api/sales/sale-history", headers=self.admin_headers)
        self.assertIn(response.status_code, (400, 409), response.text)
        self.assertIsNotNone(run(self.db.projects.find_one({"id": "project-history"})))

    def test_client_view_permission_does_not_grant_note_write_permission(self):
        run(self.db.clients.insert_one({"id": "client-own", "company_id": "company-a", "name": "Own Client"}))
        run(self.db.sales.insert_one({
            "id": "sale-own", "company_id": "company-a", "client_id": "client-own",
            "commercial_user_id": "commercial-a", "commercial": "Sales A",
        }))
        response = self.client.post(
            "/api/clients/client-own/notes", headers=self.commercial_headers, json={"text": "unauthorized write"},
        )
        self.assertEqual(response.status_code, 403, response.text)

    def test_correct_password_is_not_denied_by_an_attacker_lockout(self):
        for _ in range(server._LOGIN_MAX_ATTEMPTS):
            self.client.post("/api/auth/login", json={
                "email": self.admin["email"], "password": "definitely-wrong-password",
            })
        response = self.client.post("/api/auth/login", json={
            "email": self.admin["email"], "password": "correct-password-admin-round-three",
        })
        self.assertEqual(response.status_code, 200, response.text)

    def test_single_day_future_project_cannot_be_completed_early(self):
        photo = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
        run(self.db.projects.insert_one({
            "id": "future-project", "company_id": "company-a", "client_id": "client-future",
            "status": "en_cours", "scheduled_date": "2099-01-01", "duration_days": 1,
            "assigned_to": ["Tech A"], "photos": [],
        }))
        response = self.client.post(
            "/api/projects/future-project/complete", headers=self.tech_headers,
            json={"photos": [photo], "note": "done early"},
        )
        self.assertEqual(response.status_code, 400, response.text)


class CounterAuditValidationChecks(unittest.TestCase):
    def test_client_import_has_explicit_row_column_and_cell_bounds(self):
        with self.assertRaises((ValidationError, ValueError)):
            server.ClientImportExecuteIn(
                mapping={"0": "name"}, rows=[["x" * 100_000] for _ in range(100_000)],
            )


class CounterAuditStaticChecks(unittest.TestCase):
    def test_ai_session_draft_is_partitioned_by_authenticated_user(self):
        self.assertRegex(AI_HELPER_SOURCE, r"DRAFT_KEY[^\n]*(?:user|userId|user\.id)")

    def test_logout_clears_sensitive_session_storage(self):
        logout_block = AUTH_SOURCE.split("const logout", 1)[1].split("const can", 1)[0]
        self.assertTrue(
            "sessionStorage.clear" in logout_block
            or "kylot_ai_draft_v1" in logout_block
            or "kylot_prefill_sale" in logout_block
        )

    def test_automatic_session_expiry_clears_offline_and_draft_data(self):
        interceptor = API_SOURCE.split("api.interceptors.response.use", 1)[1]
        self.assertIn("clearSensitiveClientState", interceptor)

    def test_import_preview_does_not_echo_the_entire_uploaded_dataset(self):
        parse_block = SERVER_SOURCE.split("async def parse_import_file", 1)[1].split(
            "class ClientImportExecuteIn", 1
        )[0]
        self.assertNotIn('"rows_full": normalized', parse_block)

    def test_xlsx_parser_caps_sheet_dimensions_before_iteration(self):
        xlsx_block = SERVER_SOURCE.split("def _read_xlsx_bytes", 1)[1].split(
            "async def parse_import_file", 1
        )[0]
        self.assertTrue("max_row" in xlsx_block and "max_column" in xlsx_block)

    def test_sensitive_configuration_and_bulk_writes_are_audited(self):
        functions = (
            "execute_import_file", "create_team_member", "update_team_member", "delete_team_member",
            "create_bonus", "update_bonus", "delete_bonus", "update_settings",
        )
        missing = []
        for index, name in enumerate(functions):
            start = SERVER_SOURCE.index(f"async def {name}")
            candidates = [SERVER_SOURCE.find("\nasync def ", start + 1), SERVER_SOURCE.find("\n@api_router.", start + 1)]
            ends = [x for x in candidates if x != -1]
            end = min(ends) if ends else len(SERVER_SOURCE)
            if "log_audit(" not in SERVER_SOURCE[start:end]:
                missing.append(name)
        self.assertEqual(missing, [])

    def test_login_defence_includes_source_level_throttling(self):
        login_block = SERVER_SOURCE.split("# ---------------- Anti brute-force login", 1)[1].split(
            "# ---------------- Auth Endpoints", 1
        )[0]
        self.assertTrue(any(marker in login_block for marker in (
            "client.host", "request.client", "x-forwarded-for", "source_ip", "ip_hash",
        )))


if __name__ == "__main__":
    unittest.main(verbosity=2)
