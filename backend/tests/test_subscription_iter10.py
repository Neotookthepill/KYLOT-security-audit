"""Iteration 10 — Stripe catalog (19/39/69 €), 14-day trial, /subscription/me enrichment,
POST /api/users 402 plan gating, and regression on non-payment endpoints."""
import os
import time

import pytest
import requests
from dotenv import dotenv_values

from conftest import BASE_URL

backend_env = dotenv_values("/app/backend/.env")

EXPECTED_PRICES = {
    "keylot_small_monthly": 1900,
    "keylot_medium_monthly": 3900,
    "keylot_large_monthly": 6900,
}
EXPECTED_LIMITS = {
    "keylot_small_monthly": 5,
    "keylot_medium_monthly": 10,
    "keylot_large_monthly": None,
}


# ---------- Stripe catalog ----------
class TestStripeCatalog:
    def test_prices_amounts(self):
        key = backend_env.get("STRIPE_SECRET_KEY")
        if not key:
            pytest.skip("STRIPE_SECRET_KEY missing")
        import stripe
        stripe.api_key = key
        for lookup, amount in EXPECTED_PRICES.items():
            data = stripe.Price.list(lookup_keys=[lookup], active=True, limit=1).data
            assert data, f"No active price for {lookup}"
            p = data[0]
            assert p.unit_amount == amount, f"{lookup} = {p.unit_amount} cents, expected {amount}"
            assert p.currency == "eur"
            assert p.recurring and p.recurring["interval"] == "month"


# ---------- Checkout + trial ----------
class TestCheckoutTrial:
    @pytest.mark.parametrize("lookup", list(EXPECTED_PRICES.keys()))
    def test_checkout_returns_trial_14(self, admin_client, lookup):
        r = admin_client.post(f"{BASE_URL}/api/payments/checkout",
                              json={"lookup_key": lookup, "origin_url": "https://example.com"}, timeout=60)
        assert r.status_code == 200, f"{lookup} -> {r.status_code}: {r.text[:300]}"
        d = r.json()
        assert d.get("checkout_url", "").startswith("https://")
        assert isinstance(d.get("session_id"), str) and d["session_id"].startswith("cs_")
        # admin has no active sub -> trial 14
        assert d.get("trial_days") == 14, f"expected trial_days 14, got {d.get('trial_days')}"

    def test_no_double_trial_when_active(self, admin_client, test_credentials):
        db = _mongo()
        email = test_credentials["email"]
        doc = db.users.find_one({"email": email})
        orig_plan, orig_status = doc.get("subscription_plan"), doc.get("subscription_status")
        try:
            db.users.update_one({"email": email}, {"$set": {"subscription_plan": "keylot_medium_monthly",
                                                            "subscription_status": "active"}})
            r = admin_client.post(f"{BASE_URL}/api/payments/checkout",
                                  json={"lookup_key": "keylot_large_monthly", "origin_url": "https://example.com"},
                                  timeout=60)
            assert r.status_code == 200, r.text[:300]
            assert r.json().get("trial_days") == 0, f"double trial granted: {r.json()}"
        finally:
            db.users.update_one({"email": email}, {"$set": {"subscription_plan": orig_plan,
                                                            "subscription_status": orig_status}})

    def test_checkout_bad_lookup_key(self, admin_client):
        r = admin_client.post(f"{BASE_URL}/api/payments/checkout",
                              json={"lookup_key": "does_not_exist", "origin_url": "https://example.com"}, timeout=60)
        assert r.status_code == 400, r.text[:300]
        assert "introuvable" in r.json().get("detail", "").lower()

    def test_checkout_requires_auth(self, api_client):
        r = api_client.post(f"{BASE_URL}/api/payments/checkout",
                            json={"lookup_key": "keylot_small_monthly", "origin_url": "https://example.com"}, timeout=30)
        assert r.status_code in (401, 403), r.status_code

    def test_payment_status_unknown_session(self, api_client):
        r = api_client.get(f"{BASE_URL}/api/payments/status/cs_test_unknown_xyz", timeout=30)
        assert r.status_code in (404, 400), r.status_code


# ---------- /subscription/me ----------
class TestSubscriptionMe:
    def test_shape(self, admin_client):
        r = admin_client.get(f"{BASE_URL}/api/subscription/me", timeout=30)
        assert r.status_code == 200, r.text[:300]
        d = r.json()
        for k in ("plan", "status", "active_users", "user_limit",
                  "period_start", "period_end", "trial_end", "cancel_at_period_end"):
            assert k in d, f"missing key {k} in {d}"
        assert isinstance(d["active_users"], int) and d["active_users"] >= 1
        assert isinstance(d["cancel_at_period_end"], bool)
        if d["plan"] is None:
            assert d["user_limit"] is None

    def test_requires_auth(self, api_client):
        r = api_client.get(f"{BASE_URL}/api/subscription/me", timeout=30)
        assert r.status_code in (401, 403)


# ---------- 402 plan gating on POST /api/users ----------
def _mongo():
    from pymongo import MongoClient
    url = backend_env.get("MONGO_URL") or os.environ.get("MONGO_URL")
    dbname = backend_env.get("DB_NAME") or os.environ.get("DB_NAME")
    if not url or not dbname:
        pytest.skip("MONGO_URL/DB_NAME missing")
    return MongoClient(url)[dbname]


class TestUserLimitGating:
    def test_no_plan_allows_creation_then_402_when_limited(self, admin_client, test_credentials):
        db = _mongo()
        email = test_credentials["email"]
        admin_doc = db.users.find_one({"email": email})
        assert admin_doc, "admin not found in DB"
        orig_plan = admin_doc.get("subscription_plan")
        orig_status = admin_doc.get("subscription_status")
        created = []
        try:
            # 1) No plan -> creation succeeds
            db.users.update_one({"email": email}, {"$set": {"subscription_plan": None, "subscription_status": None}})
            ts = int(time.time())
            payload = {"name": "TEST_ITER10", "email": f"test_iter10_{ts}@example.com",
                       "password": "Test@2026", "role": "technicien"}
            r = admin_client.post(f"{BASE_URL}/api/users", json=payload, timeout=30)
            assert r.status_code in (200, 201), f"unlimited create failed {r.status_code}: {r.text[:300]}"
            body = r.json()
            uid = body.get("id") or body.get("user", {}).get("id")
            if uid:
                created.append(uid)
            # verify persistence
            lr = admin_client.get(f"{BASE_URL}/api/users", timeout=30)
            assert lr.status_code == 200
            assert any(u["email"] == payload["email"] for u in lr.json()), "created user not persisted"

            total = db.users.count_documents({})

            # 2) Plan whose limit is already reached -> 402
            #    small plan limit = 5; ensure current count >= limit by picking small plan
            assert total >= 5, f"only {total} users; cannot exercise small-plan limit"
            db.users.update_one({"email": email}, {"$set": {"subscription_plan": "keylot_small_monthly",
                                                            "subscription_status": "active"}})
            r2 = admin_client.post(f"{BASE_URL}/api/users", json={
                "name": "TEST_ITER10_BLOCKED", "email": f"test_iter10_blocked_{ts}@example.com",
                "password": "Test@2026", "role": "technicien"}, timeout=30)
            assert r2.status_code == 402, f"expected 402, got {r2.status_code}: {r2.text[:300]}"
            detail = r2.json().get("detail", "")
            assert "Limite du plan atteinte" in detail, detail

            # 3) /subscription/me now reflects plan + limit
            sr = admin_client.get(f"{BASE_URL}/api/subscription/me", timeout=30)
            assert sr.status_code == 200
            sd = sr.json()
            assert sd["plan"] == "keylot_small_monthly"
            assert sd["user_limit"] == EXPECTED_LIMITS["keylot_small_monthly"]
            assert sd["status"] == "active"

            # 4) large plan (unlimited) -> creation allowed again
            db.users.update_one({"email": email}, {"$set": {"subscription_plan": "keylot_large_monthly",
                                                            "subscription_status": "active"}})
            sr2 = admin_client.get(f"{BASE_URL}/api/subscription/me", timeout=30)
            assert sr2.json()["user_limit"] is None
            r3 = admin_client.post(f"{BASE_URL}/api/users", json={
                "name": "TEST_ITER10_UNLIM", "email": f"test_iter10_unlim_{ts}@example.com",
                "password": "Test@2026", "role": "technicien"}, timeout=30)
            assert r3.status_code in (200, 201), f"unlimited plan create failed {r3.status_code}: {r3.text[:300]}"
            b3 = r3.json()
            uid3 = b3.get("id") or b3.get("user", {}).get("id")
            if uid3:
                created.append(uid3)
        finally:
            for uid in created:
                admin_client.delete(f"{BASE_URL}/api/users/{uid}", timeout=30)
            db.users.delete_many({"email": {"$regex": "^test_iter10_"}})
            db.users.update_one({"email": email}, {"$set": {"subscription_plan": orig_plan,
                                                            "subscription_status": orig_status}})
            restored = db.users.find_one({"email": email})
            assert restored.get("subscription_plan") == orig_plan


# ---------- Regression on non-payment endpoints ----------
REGRESSION_GET = [
    "/api/auth/me", "/api/users", "/api/clients", "/api/sales", "/api/projects",
    "/api/commissions", "/api/dashboard/stats", "/api/team", "/api/settings",
    "/api/reports/monthly?month=2026-07", "/api/overtime?month=2026-07",
]


class TestRegression:
    @pytest.mark.parametrize("path", REGRESSION_GET)
    def test_get_200(self, admin_client, path):
        r = admin_client.get(f"{BASE_URL}{path}", timeout=45)
        assert r.status_code == 200, f"{path} -> {r.status_code}: {r.text[:200]}"

    def test_no_mongo_object_id_leak(self, admin_client):
        for path in ("/api/users", "/api/clients", "/api/sales"):
            r = admin_client.get(f"{BASE_URL}{path}", timeout=45)
            if r.status_code == 200 and isinstance(r.json(), list) and r.json():
                assert "_id" not in r.json()[0], f"{path} leaks _id"
