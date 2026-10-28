"""Route inventory, business integrity and bounded-structure checks."""

from __future__ import annotations

import asyncio
import math
import os
import re
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch


os.environ.update({
    "ENVIRONMENT": "production",
    "MONGO_URL": "mongodb://127.0.0.1:27017",
    "DB_NAME": "kylot_route_business_fuzz",
    "JWT_SECRET": "route-business-fuzz-secret-at-least-32-characters",
    "FRONTEND_URL": "https://app.example.invalid",
    "CORS_ORIGINS": "https://app.example.invalid",
    "ALLOW_PUBLIC_REGISTRATION": "false",
    "ALLOW_DEMO_DATA": "false",
    "ALLOW_TOKEN_RESPONSE": "false",
    "RUN_STARTUP_MIGRATIONS": "false",
    "EXPOSE_API_DOCS": "false",
    "COOKIE_SECURE": "true",
    "COOKIE_SAMESITE": "lax",
    "WEBHOOK_CRON_SECRET": "route-audit-cron-secret",
    "STRIPE_WEBHOOK_SECRET": "whsec_route_audit_placeholder",
})

from fastapi.routing import APIRoute
from fastapi.testclient import TestClient
from mongomock_motor import AsyncMongoMockClient
from pydantic import ValidationError
from fastapi import HTTPException

from backend import server


def run(coro):
    return asyncio.run(coro)


def dependency_names(dependant) -> set[str]:
    names: set[str] = set()
    for dependency in dependant.dependencies:
        names.add(getattr(dependency.call, "__name__", ""))
        names.update(dependency_names(dependency))
    return names


PUBLIC_API_ROUTES = {
    ("POST", "/api/auth/register"),
    ("POST", "/api/auth/login"),
    ("POST", "/api/auth/logout"),
    ("POST", "/api/cron/rappel-chantiers-j1"),
    ("POST", "/api/cron/bilan-mensuel"),
    ("POST", "/api/stripe/webhook"),
}


class RouteInventoryChecks(unittest.TestCase):
    def setUp(self):
        self.mongo = AsyncMongoMockClient()
        self.db = self.mongo["kylot_route_business_fuzz"]
        server.db = self.db
        server.client = self.mongo
        self.client = TestClient(server.app)

    def tearDown(self):
        self.client.close()
        self.mongo.close()

    def test_every_api_route_is_authenticated_or_explicitly_public(self):
        routes = [route for route in server.api_router.routes if isinstance(route, APIRoute)]
        self.assertGreaterEqual(len(routes), 160)
        seen: set[tuple[str, str]] = set()
        for route in routes:
            for method in route.methods:
                key = (method, route.path)
                self.assertNotIn(key, seen, f"Route dupliquée: {key}")
                seen.add(key)
                dependencies = dependency_names(route.dependant)
                protected = bool(dependencies & {"get_current_user", "require_admin", "require_super_admin"})
                self.assertTrue(protected or key in PUBLIC_API_ROUTES, f"Route sans garde explicite: {key}")

    def test_all_centrally_protected_routes_reject_anonymous_requests(self):
        checked = 0
        for route in server.api_router.routes:
            if not isinstance(route, APIRoute):
                continue
            dependencies = dependency_names(route.dependant)
            if not dependencies & {"get_current_user", "require_admin", "require_super_admin"}:
                continue
            path = re.sub(r"\{[^}]+\}", "00000000-0000-0000-0000-000000000000", route.path)
            method = sorted(route.methods)[0].lower()
            response = self.client.request(method.upper(), path, json={} if method in {"post", "put", "patch"} else None)
            self.assertEqual(response.status_code, 401, f"{method.upper()} {route.path}: {response.status_code} {response.text}")
            checked += 1
        self.assertGreaterEqual(checked, 150)

    def test_public_technical_routes_fail_closed_without_their_secret(self):
        self.assertEqual(self.client.post("/api/auth/register", json={"name": "A", "email": "a@example.com", "password": "long-password"}).status_code, 403)
        self.assertIn(self.client.post("/api/cron/rappel-chantiers-j1", json={}).status_code, {401, 403})
        self.assertIn(self.client.post("/api/cron/bilan-mensuel", json={}).status_code, {401, 403})
        self.assertGreaterEqual(self.client.post("/api/stripe/webhook", content=b"{}").status_code, 400)


class BusinessIntegrityChecks(unittest.TestCase):
    def test_impossible_dates_and_times_are_rejected(self):
        invalid_factories = [
            lambda: server.AbsenceIn(person_name="A", person_type="technicien", date_from="2026-02-31", date_to="2026-03-01"),
            lambda: server.AbsenceIn(person_name="A", person_type="technicien", date_from="2026-10-19", date_to="2026-10-19", all_day=False, start_time="25:99", end_time="26:00"),
            lambda: server.AbsenceIn(person_name="A", person_type="technicien", date_from="2026-10-20", date_to="2026-10-19"),
            lambda: server.ReinterventionIn(client_id="c", scheduled_date="2026-02-31", scheduled_time="99:99"),
            lambda: server.ReinterventionUpdate(scheduled_date="2025-13-01"),
            lambda: server.OffDayIn(date="2026-02-31", scope="company"),
            lambda: server.ProjectUpdate(extra_dates=["2026-02-31"]),
            lambda: server.ProjectUpdate(day_exclusions={"2026-13-01": ["Tech"]}),
        ]
        for factory in invalid_factories:
            with self.subTest(factory=factory):
                with self.assertRaises(ValidationError):
                    factory()

    def test_nested_business_collections_are_bounded(self):
        cases = [
            lambda: server.SaleIn(service="S", sale_date="2026-10-19", prestations=[{"name": "P"}] * 101),
            lambda: server.ClientCategoryPayload(categories=[{"key": f"c{i}", "label": "C"} for i in range(101)]),
            lambda: server.ClientCategoryIn(key="c", label="C", sub_statuses=[{"key": f"s{i}", "label": "S"} for i in range(101)]),
            lambda: server.AIMemoryIn(content="ok", tags=["tag"] * 9),
            lambda: server.ProjectUpdate(photos=["https://cdn.example.invalid/a.png"] * 21),
            lambda: server.ReinterventionIn(client_id="c", scheduled_date="2026-10-19", photos=["https://cdn.example.invalid/a.png"] * 21),
            lambda: server.ProjectCompleteIn(photos=["https://cdn.example.invalid/a.png"] * 21),
            lambda: server.SaleStatusesIn(statuses=[{"value": f"s{i}", "label": "S"} for i in range(101)]),
            lambda: server.BonusIn(name="B", ca_threshold=1, amount=1, commerciaux=["A"] * 501),
            lambda: server.SettingsIn(overtime_eligible=["A"] * 501),
            lambda: server.SettingsIn(commission_rates=[0.1] * 101),
            lambda: server.SettingsIn(sale_status_order=["a"] * 101),
            lambda: server.SettingsIn(commission_discount_tiers=[{}] * 101),
            lambda: server.SettingsIn(prospect_mgr_bonuses=[{}] * 101),
        ]
        for factory in cases:
            with self.subTest(factory=factory):
                with self.assertRaises(ValidationError):
                    factory()

    def test_non_finite_financial_values_are_rejected(self):
        for value in (math.nan, math.inf, -math.inf):
            with self.subTest(value=value):
                with self.assertRaises(ValidationError):
                    server.SaleIn(service="S", sale_date="2026-10-19", amount=value)
                with self.assertRaises(ValidationError):
                    server.SaleIn(service="S", sale_date="2026-10-19", commission_rate=value)

    def test_financial_and_month_cross_field_invariants(self):
        invalid_factories = [
            lambda: server.SaleIn(service="S", sale_date="2026-10-19", amount=100, financement_amount=101),
            lambda: server.SaleIn(service="S", sale_date="2026-10-19", commission_month="2026-13"),
            lambda: server.SaleIn(service="S", sale_date="2026-10-19", desired_intervention_date="2026-02-31"),
            lambda: server.SaleUpdate(amount=100, financement_amount=101),
            lambda: server.SaleUpdate(commission_month="not-a-month"),
            lambda: server.ProspectCommissionIn(prospect_commission_month="2026-13"),
            lambda: server.OvertimeValidateTechIn(technician_name="A", month="2026-13"),
        ]
        for factory in invalid_factories:
            with self.subTest(factory=factory):
                with self.assertRaises(ValidationError):
                    factory()

    def test_nested_strings_are_bounded(self):
        cases = [
            lambda: server.AIMemoryIn(content="ok", tags=["A" * 51]),
            lambda: server.BonusIn(name="B", ca_threshold=1, amount=1, commerciaux=["A" * 121]),
            lambda: server.ProjectUpdate(extra_dates=["A" * 11]),
            lambda: server.ProjectUpdate(day_exclusions={"2026-10-19": ["A" * 121]}),
        ]
        for factory in cases:
            with self.subTest(factory=factory):
                with self.assertRaises(ValidationError):
                    factory()

    def test_remaining_public_models_reject_unbounded_or_invalid_values(self):
        cases = [
            lambda: server.MonthlyReportIn(month="2026-13"),
            lambda: server.ClientCategoryIn(key="c", label="C", color="javascript:alert(1)"),
            lambda: server.ClientCategoryAssign(category_key="A" * 41),
            lambda: server.ClientImportExecuteIn(import_id="0" * 36, assign_category="A" * 41),
            lambda: server.ClientPdfCreateIn(name="A" * 201),
            lambda: server.ClientPdfCreateIn(name="A", devis_date="2026-02-31"),
            lambda: server.KiksActIn(message="ok", page="A" * 121),
            lambda: server.AIActionExecuteIn(intent="delete_everything", data={}),
            lambda: server.TeamMemberIn(name="A", type="root"),
            lambda: server.UserCreateIn(email="a@example.com", password="long-password", name="A", role="root"),
            lambda: server.CronReminderIn(run_id="A" * 201),
            lambda: server.CheckoutRequest(lookup_key="A" * 121, origin_url="https://app.example.invalid"),
            lambda: server.PortalRequest(return_url="A" * 2049),
            lambda: server.BindCommercialIn(user_id="A" * 129),
            lambda: server.SaleStatusItem(value="ok", label="OK", color="url(evil)"),
            lambda: server.StockHolderIn(user_id="u", quantity=100001),
            lambda: server.StockTransferIn(from_user_id=None, to_user_id="u", quantity=100001),
            lambda: server.UserPermissionsIn(permissions={"unknown": {"root": True}}),
            lambda: server.UserPermissionsIn(permissions={"clients": {"view": "god"}}),
            lambda: server.SettingsIn(notifications={"unknown": True}),
            lambda: server.SettingsIn(dashboard_widgets={"evil": True}),
            lambda: server.SettingsIn(commission_discount_tiers=[{"max_discount": 10, "rate": 2}]),
            lambda: server.SettingsIn(prospect_mgr_bonuses=[{"name": "B", "metric": "root", "threshold": 1, "amount": 1}]),
        ]
        for factory in cases:
            with self.subTest(factory=factory):
                with self.assertRaises(ValidationError):
                    factory()

    def test_all_month_filters_reject_regexes_and_impossible_months(self):
        for value in (".*", "2026-13", "2026-00", "2026-1", "2026-10.*"):
            with self.subTest(value=value):
                with self.assertRaises(HTTPException):
                    server._validated_month(value)
        self.assertEqual(server._validated_month("2026-10"), "2026-10")

    def test_production_html_does_not_load_session_replay_or_builder_runtime(self):
        html = (Path(__file__).parents[1] / "frontend" / "public" / "index.html").read_text(encoding="utf-8").lower()
        self.assertNotIn("posthog", html)
        self.assertNotIn("assets.emergent.sh", html)
        self.assertNotIn("session_recording", html)

    def test_offline_replay_waits_for_confirmed_server_identity(self):
        root = Path(__file__).parents[1] / "frontend" / "src"
        offline = (root / "lib" / "offline.js").read_text(encoding="utf-8")
        api = (root / "lib" / "api.js").read_text(encoding="utf-8")
        auth = (root / "contexts" / "AuthContext.jsx").read_text(encoding="utf-8")
        self.assertIn("let identity = null", offline)
        self.assertIn("if (running || !identity || !navigator.onLine) return", offline)
        self.assertNotIn("refreshPending().then(() => syncOffline())", api)
        self.assertIn("setOfflineIdentity(r.data?.id)", auth)
        self.assertIn("syncOffline()", auth)

    def test_service_worker_does_not_persist_third_party_resources(self):
        source = (Path(__file__).parents[1] / "frontend" / "public" / "sw.js").read_text(encoding="utf-8")
        self.assertIn("url.origin === self.location.origin", source)
        self.assertNotIn("tile\\.openstreetmap", source)
        self.assertNotIn("fonts\\.(googleapis|gstatic)", source)
        self.assertNotIn("cdnjs\\.cloudflare", source)

    def test_external_ai_fails_closed_in_production_without_explicit_opt_in(self):
        self.assertFalse(server._external_ai_enabled())
        with self.assertRaisesRegex(Exception, "désactivées"):
            server._require_external_ai_enabled()

    def test_completion_email_encodes_all_business_controlled_values(self):
        attack = '<img src="https://tracker.example/pixel" onerror="alert(1)">'
        html = server._completion_commercial_email_html(
            client_name=attack,
            address=attack,
            completed_by=attack,
            completed_at=attack,
            note=attack,
            photo_count=1,
        )
        self.assertNotIn("<img", html.lower())
        scan = server._EmailScan()
        scan.feed(html)
        self.assertNotIn("img", scan.tags)
        self.assertFalse(scan.dangerous_attrs)
        self.assertIn("&lt;img", html.lower())
        self.assertGreaterEqual(html.count("&lt;img"), 5)
        server._assert_safe_email("Chantier terminé", html)

    def test_email_guard_rejects_active_content_tracking_and_event_handlers(self):
        hostile = [
            '<script>alert(1)</script>',
            '<img src="https://tracker.example/pixel">',
            '<p onclick="alert(1)">Cliquez</p>',
            '<style>body{display:none}</style>',
            '<iframe src="https://example.com"></iframe>',
        ]
        for html in hostile:
            with self.subTest(html=html):
                with self.assertRaises(ValueError):
                    server._assert_safe_email("Sujet", html)


class AuthorizationAndPaymentRegressionChecks(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.mongo = AsyncMongoMockClient()
        self.db = self.mongo["kylot_route_business_regressions"]
        server.db = self.db
        server.client = self.mongo
        self.company = "company-a"

    async def asyncTearDown(self):
        self.mongo.close()

    async def test_note_deletion_requires_current_client_edit_permission(self):
        user = {
            "id": "commercial-a", "name": "Commercial A", "role": "commercial",
            "company_id": self.company, "permissions": {"clients": {"view": "own", "edit": False}},
        }
        await self.db.clients.insert_one({"id": "client-a", "company_id": self.company})
        await self.db.client_notes.insert_one({
            "id": "note-a", "client_id": "client-a", "company_id": self.company, "author_id": user["id"],
        })
        with self.assertRaises(HTTPException) as raised:
            await server.delete_client_note("note-a", user)
        self.assertEqual(raised.exception.status_code, 403)
        self.assertIsNotNone(await self.db.client_notes.find_one({"id": "note-a"}))

    async def test_global_search_obeys_revoked_permissions_and_own_scope(self):
        await self.db.clients.insert_one({
            "id": "client-secret", "company_id": self.company, "name": "Needle Client",
        })
        await self.db.sales.insert_one({
            "id": "sale-secret", "company_id": self.company, "client_id": "client-secret",
            "client_name": "Needle Client", "service": "Needle Service",
            "commercial_user_id": "other-commercial",
        })
        await self.db.projects.insert_one({
            "id": "project-secret", "company_id": self.company, "client_id": "client-secret",
            "sale_id": "sale-secret", "client_name": "Needle Client", "service": "Needle Project",
            "assigned_to": ["Other Tech"],
        })
        await self.db.reinterventions.insert_one({
            "id": "re-secret", "company_id": self.company, "client_name": "Needle Client",
            "reason": "Needle Reason", "assigned_to": "Other Tech",
        })
        await self.db.users.insert_one({
            "id": "user-secret", "company_id": self.company, "name": "Needle User",
            "email": "needle@example.com", "role": "commercial",
        })

        denied = {
            "id": "commercial-a", "name": "Commercial A", "role": "commercial",
            "company_id": self.company,
            "permissions": {
                "clients": {"view": "none"}, "sales": {"view": "none"},
                "projects": {"view": "none"}, "planning": {"view": "none"},
                "users": {"manage": False},
            },
        }
        result = await server.global_search("Needle", 20, denied)
        self.assertEqual(result["total"], 0)
        self.assertTrue(all(not rows for rows in result["categories"].values()))

        own_only = {
            **denied,
            "permissions": {
                **denied["permissions"],
                "clients": {"view": "own"}, "sales": {"view": "own"},
                "projects": {"view": "own"}, "planning": {"view": "own"},
            },
        }
        result = await server.global_search("Needle", 20, own_only)
        self.assertEqual(result["total"], 0)

    async def test_global_search_hides_user_directory_without_manage_permission(self):
        await self.db.users.insert_one({
            "id": "user-secret", "company_id": self.company, "name": "Directory Needle",
            "email": "directory@example.com", "role": "commercial",
        })
        manager = {
            "id": "responsable-a", "name": "Manager", "role": "responsable",
            "company_id": self.company,
            "permissions": server.get_default_permissions("responsable"),
        }
        result = await server.global_search("Directory Needle", 20, manager)
        self.assertEqual(result["categories"]["users"], [])

    async def test_stock_compare_and_set_preserves_simultaneous_increments(self):
        user = {"id": "admin-a", "role": "admin", "company_id": self.company}
        await self.db.stock.insert_one({
            "id": "stock-a", "company_id": self.company, "product_key": "p",
            "product_name": "P", "stock_disponible": 0, "_rev": 0,
        })

        def mutate(row):
            return ({"stock_disponible": int(row.get("stock_disponible") or 0) + 1}, {})

        await asyncio.gather(*[
            server._stock_compare_and_set("stock-a", user, mutate, attempts=50)
            for _ in range(20)
        ])
        stored = await self.db.stock.find_one({"id": "stock-a"})
        self.assertEqual(stored["stock_disponible"], 20)
        self.assertEqual(stored["_rev"], 20)

    async def test_cookie_auth_rejects_cross_site_writes_but_bearer_clients_remain_supported(self):
        user = {
            "id": "admin-origin", "email": "origin@example.invalid", "name": "Origin",
            "role": "admin", "company_id": self.company, "is_active": True,
        }
        await self.db.users.insert_one(user.copy())
        token = server.create_access_token(user["id"], user["email"])

        def request(headers):
            raw = [(k.lower().encode(), v.encode()) for k, v in headers.items()]
            return server.Request({
                "type": "http", "http_version": "1.1", "method": "POST",
                "scheme": "https", "path": "/api/me/onboarding-complete",
                "raw_path": b"/api/me/onboarding-complete", "query_string": b"",
                "headers": raw, "client": ("127.0.0.1", 1234), "server": ("testserver", 443),
            })

        hostile = request({
            "cookie": f"access_token={token}", "origin": "https://evil.example",
            "sec-fetch-site": "cross-site",
        })
        with self.assertRaises(HTTPException) as raised:
            await server.get_current_user(hostile)
        self.assertEqual(raised.exception.status_code, 403)

        bearer = request({"authorization": f"Bearer {token}", "origin": "https://evil.example"})
        authenticated = await server.get_current_user(bearer)
        self.assertEqual(authenticated["id"], user["id"])

    async def test_disabled_account_is_rejected_centrally(self):
        user = {
            "id": "disabled-a", "email": "disabled@example.invalid", "name": "Disabled",
            "role": "commercial", "company_id": self.company, "is_active": False,
        }
        await self.db.users.insert_one(user.copy())
        token = server.create_access_token(user["id"], user["email"])
        request = server.Request({
            "type": "http", "http_version": "1.1", "method": "GET", "scheme": "https",
            "path": "/api/auth/me", "raw_path": b"/api/auth/me", "query_string": b"",
            "headers": [(b"authorization", f"Bearer {token}".encode())],
            "client": ("127.0.0.1", 1234), "server": ("testserver", 443),
        })
        with self.assertRaises(HTTPException) as raised:
            await server.get_current_user(request)
        self.assertEqual(raised.exception.status_code, 401)

    async def test_throttled_login_source_is_rejected_before_bcrypt(self):
        request = server.Request({
            "type": "http", "http_version": "1.1", "method": "POST", "scheme": "https",
            "path": "/api/auth/login", "raw_path": b"/api/auth/login", "query_string": b"",
            "headers": [], "client": ("127.0.0.1", 1234), "server": ("testserver", 443),
        })
        data = server.LoginIn(email="nobody@example.com", password="wrong")
        with patch.object(server, "_check_login_source", side_effect=HTTPException(status_code=429)), \
             patch.object(server, "verify_password") as verify:
            with self.assertRaises(HTTPException) as raised:
                await server.login(data, server.Response(), request)
        self.assertEqual(raised.exception.status_code, 429)
        verify.assert_not_called()

    async def test_unknown_email_still_uses_dummy_bcrypt_hash(self):
        request = server.Request({
            "type": "http", "http_version": "1.1", "method": "POST", "scheme": "https",
            "path": "/api/auth/login", "raw_path": b"/api/auth/login", "query_string": b"",
            "headers": [], "client": ("127.0.0.1", 1234), "server": ("testserver", 443),
        })
        data = server.LoginIn(email="nobody@example.com", password="wrong")
        with patch.object(server, "verify_password", return_value=False) as verify:
            with self.assertRaises(HTTPException):
                await server.login(data, server.Response(), request)
        self.assertEqual(verify.call_args.args[1], server._DUMMY_PASSWORD_HASH)

    async def test_completed_but_unpaid_checkout_does_not_grant_access(self):
        user = {"id": "admin-a", "email": "a@example.invalid", "role": "admin", "company_id": self.company}
        await self.db.payment_transactions.insert_one({
            "session_id": "cs-unpaid", "user_id": user["id"], "company_id": self.company,
            "status": "initiated", "payment_status": "pending", "lookup_key": "plan-a",
        })
        checkout = SimpleNamespace(
            payment_status="unpaid", status="complete", subscription=None,
            payment_intent=None, metadata={},
        )
        with patch.object(server.stripe.checkout.Session, "retrieve", return_value=checkout):
            result = await server.get_payment_status("cs-unpaid", user)
        self.assertFalse(result["entitled"])
        stored = await self.db.payment_transactions.find_one({"session_id": "cs-unpaid"})
        self.assertEqual(stored["payment_status"], "pending")

    async def test_trialing_subscription_is_entitled_without_faking_paid_payment(self):
        user = {"id": "admin-a", "email": "a@example.invalid", "role": "admin", "company_id": self.company}
        await self.db.users.insert_one(user.copy())
        await self.db.payment_transactions.insert_one({
            "session_id": "cs-trial", "user_id": user["id"], "company_id": self.company,
            "status": "initiated", "payment_status": "pending", "lookup_key": "plan-a",
        })
        checkout = SimpleNamespace(
            payment_status="no_payment_required", status="complete", subscription="sub-trial",
            payment_intent=None, metadata={"user_id": user["id"], "lookup_key": "plan-a"},
        )
        subscription = SimpleNamespace(status="trialing")
        with patch.object(server.stripe.checkout.Session, "retrieve", return_value=checkout), \
             patch.object(server.stripe.Subscription, "retrieve", return_value=subscription):
            result = await server.get_payment_status("cs-trial", user)
        self.assertTrue(result["entitled"])
        self.assertEqual(result["payment_status"], "no_payment_required")
        stored_user = await self.db.users.find_one({"id": user["id"]})
        self.assertEqual(stored_user["subscription_status"], "trialing")

    async def test_webhook_completed_unpaid_session_does_not_activate_user(self):
        user = {"id": "admin-a", "email": "a@example.invalid", "role": "admin", "company_id": self.company}
        await self.db.users.insert_one(user.copy())
        await self.db.payment_transactions.insert_one({
            "session_id": "cs-webhook-unpaid", "user_id": user["id"], "company_id": self.company,
            "lookup_key": "plan-a", "status": "initiated", "payment_status": "pending",
        })
        await server._process_stripe_event({
            "type": "checkout.session.completed",
            "data": {"object": {"id": "cs-webhook-unpaid", "payment_status": "unpaid", "subscription": None}},
        })
        stored_user = await self.db.users.find_one({"id": user["id"]})
        self.assertNotIn("subscription_status", stored_user)
        transaction = await self.db.payment_transactions.find_one({"session_id": "cs-webhook-unpaid"})
        self.assertEqual(transaction["status"], "pending")
        self.assertEqual(transaction["payment_status"], "unpaid")

    async def test_webhook_unknown_session_cannot_target_user_through_metadata(self):
        user = {"id": "victim", "role": "admin", "company_id": self.company}
        await self.db.users.insert_one(user.copy())
        event = {
            "type": "checkout.session.completed",
            "data": {"object": {
                "id": "cs-not-created-here", "payment_status": "paid", "subscription": None,
                "metadata": {"user_id": user["id"], "company_id": self.company, "lookup_key": "plan-a"},
            }},
        }
        with self.assertRaises(RuntimeError):
            await server._process_stripe_event(event)
        stored_user = await self.db.users.find_one({"id": user["id"]})
        self.assertNotIn("subscription_status", stored_user)

    async def test_async_payment_success_activates_matching_local_transaction(self):
        user = {"id": "admin-a", "role": "admin", "company_id": self.company}
        await self.db.users.insert_one(user.copy())
        await self.db.payment_transactions.insert_one({
            "session_id": "cs-async", "user_id": user["id"], "company_id": self.company,
            "lookup_key": "plan-a", "status": "pending", "payment_status": "unpaid",
        })
        await server._process_stripe_event({
            "type": "checkout.session.async_payment_succeeded",
            "data": {"object": {"id": "cs-async", "payment_status": "paid", "subscription": None}},
        })
        stored_user = await self.db.users.find_one({"id": user["id"]})
        self.assertEqual(stored_user["subscription_status"], "active")
        self.assertEqual(stored_user["subscription_plan"], "plan-a")

    async def test_subscription_deletion_and_past_due_update_suspend_access(self):
        user = {"id": "admin-a", "role": "admin", "company_id": self.company, "subscription_status": "active"}
        await self.db.users.insert_one(user.copy())
        await self.db.payment_transactions.insert_one({
            "session_id": "cs-sub", "user_id": user["id"], "company_id": self.company,
            "stripe_subscription_id": "sub-a", "status": "completed", "payment_status": "paid",
        })
        await server._process_stripe_event({
            "type": "customer.subscription.updated",
            "data": {"object": {"id": "sub-a", "status": "past_due"}},
        })
        stored_user = await self.db.users.find_one({"id": user["id"]})
        self.assertEqual(stored_user["subscription_status"], "suspended")
        await self.db.users.update_one({"id": user["id"]}, {"$set": {"subscription_status": "active"}})
        await server._process_stripe_event({
            "type": "customer.subscription.deleted", "data": {"object": {"id": "sub-a"}},
        })
        stored_user = await self.db.users.find_one({"id": user["id"]})
        self.assertEqual(stored_user["subscription_status"], "suspended")

    async def test_full_refund_and_dispute_suspend_only_matching_payment_owner(self):
        owner = {"id": "owner", "role": "admin", "company_id": self.company, "subscription_status": "active"}
        other = {"id": "other", "role": "admin", "company_id": self.company, "subscription_status": "active"}
        await self.db.users.insert_many([owner.copy(), other.copy()])
        await self.db.payment_transactions.insert_one({
            "session_id": "cs-refund", "user_id": owner["id"], "company_id": self.company,
            "stripe_payment_intent_id": "pi-owner", "status": "completed", "payment_status": "paid",
        })
        await server._process_stripe_event({
            "type": "charge.refunded",
            "data": {"object": {"payment_intent": "pi-owner", "refunded": True}},
        })
        stored_owner = await self.db.users.find_one({"id": owner["id"]})
        stored_other = await self.db.users.find_one({"id": other["id"]})
        transaction = await self.db.payment_transactions.find_one({"session_id": "cs-refund"})
        self.assertEqual(stored_owner["subscription_status"], "suspended")
        self.assertEqual(stored_other["subscription_status"], "active")
        self.assertEqual(transaction["payment_status"], "refunded")
        await self.db.users.update_one({"id": owner["id"]}, {"$set": {"subscription_status": "active"}})
        await server._process_stripe_event({
            "type": "charge.dispute.created",
            "data": {"object": {"payment_intent": "pi-owner"}},
        })
        stored_owner = await self.db.users.find_one({"id": owner["id"]})
        transaction = await self.db.payment_transactions.find_one({"session_id": "cs-refund"})
        self.assertEqual(stored_owner["subscription_status"], "suspended")
        self.assertEqual(transaction["payment_status"], "disputed")

    async def test_partial_refund_does_not_suspend_access(self):
        user = {"id": "admin-a", "role": "admin", "company_id": self.company, "subscription_status": "active"}
        await self.db.users.insert_one(user.copy())
        await self.db.payment_transactions.insert_one({
            "session_id": "cs-partial", "user_id": user["id"], "company_id": self.company,
            "stripe_payment_intent_id": "pi-partial", "status": "completed", "payment_status": "paid",
        })
        await server._process_stripe_event({
            "type": "charge.refunded",
            "data": {"object": {"payment_intent": "pi-partial", "refunded": False}},
        })
        stored_user = await self.db.users.find_one({"id": user["id"]})
        transaction = await self.db.payment_transactions.find_one({"session_id": "cs-partial"})
        self.assertEqual(stored_user["subscription_status"], "active")
        self.assertEqual(transaction["payment_status"], "partially_refunded")

    async def test_expired_checkout_is_closed_without_touching_user(self):
        user = {"id": "admin-a", "role": "admin", "company_id": self.company}
        await self.db.users.insert_one(user.copy())
        await self.db.payment_transactions.insert_one({
            "session_id": "cs-expired", "user_id": user["id"], "company_id": self.company,
            "status": "initiated", "payment_status": "pending",
        })
        await server._process_stripe_event({
            "type": "checkout.session.expired", "data": {"object": {"id": "cs-expired"}},
        })
        transaction = await self.db.payment_transactions.find_one({"session_id": "cs-expired"})
        stored_user = await self.db.users.find_one({"id": user["id"]})
        self.assertEqual(transaction["status"], "expired")
        self.assertEqual(transaction["payment_status"], "unpaid")
        self.assertNotIn("subscription_status", stored_user)


if __name__ == "__main__":
    unittest.main(verbosity=2)
