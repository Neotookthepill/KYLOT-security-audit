"""Iteration 2 regression suite: commissions route restore + related regressions."""
import os
import re
import uuid

import pytest
import requests
from dotenv import dotenv_values

frontend_env = dotenv_values("/app/frontend/.env")
BASE_URL = (os.environ.get("REACT_APP_BACKEND_URL") or frontend_env["REACT_APP_BACKEND_URL"]).rstrip("/")


# ---------------- Module: Commissions (the bug fix) ----------------
class TestCommissions:
    def test_get_commissions_200_list(self, admin_client):
        r = admin_client.get(f"{BASE_URL}/api/commissions", timeout=30)
        assert r.status_code == 200, f"{r.status_code}: {r.text[:300]}"
        data = r.json()
        assert isinstance(data, list), f"expected list got {type(data)}"
        assert len(data) > 0, "commissions list is empty - cannot verify shape"
        row = data[0]
        for k in ("sale_id", "sale_date", "client_name", "amount", "commission_rate",
                  "commission_amount", "commission_paid", "commission_month", "status"):
            assert k in row, f"missing key {k} in {row}"
        assert "_id" not in row
        assert isinstance(row["commission_paid"], bool)
        # commission_amount consistency
        for row in data:
            assert abs(row["commission_amount"] - round(row["amount"] * row["commission_rate"], 2)) < 0.011, row

    def test_commissions_requires_auth(self):
        r = requests.get(f"{BASE_URL}/api/commissions", timeout=30)
        assert r.status_code in (401, 403), r.status_code

    def test_toggle_commission_paid_persists(self, admin_client):
        rows = admin_client.get(f"{BASE_URL}/api/commissions", timeout=30).json()
        assert rows
        row = rows[0]
        sid = row["sale_id"]
        original = row["commission_paid"]
        try:
            r = admin_client.put(f"{BASE_URL}/api/sales/{sid}", json={"commission_paid": not original}, timeout=30)
            assert r.status_code == 200, f"{r.status_code}: {r.text[:300]}"
            assert r.json().get("commission_paid") is (not original)
            after = admin_client.get(f"{BASE_URL}/api/commissions", timeout=30).json()
            found = [x for x in after if x["sale_id"] == sid][0]
            assert found["commission_paid"] is (not original), "toggle not persisted in /commissions"
        finally:
            admin_client.put(f"{BASE_URL}/api/sales/{sid}", json={"commission_paid": original}, timeout=30)

    def test_update_commission_rate_recomputes_amount(self, admin_client):
        rows = admin_client.get(f"{BASE_URL}/api/commissions", timeout=30).json()
        row = next((x for x in rows if x["amount"] > 0), None)
        assert row, "no sale with amount > 0"
        sid, original_rate = row["sale_id"], row["commission_rate"]
        new_rate = 0.20 if original_rate != 0.20 else 0.15
        try:
            r = admin_client.put(f"{BASE_URL}/api/sales/{sid}", json={"commission_rate": new_rate}, timeout=30)
            assert r.status_code == 200, r.text[:300]
            after = admin_client.get(f"{BASE_URL}/api/commissions", timeout=30).json()
            found = [x for x in after if x["sale_id"] == sid][0]
            assert abs(found["commission_rate"] - new_rate) < 1e-6
            assert abs(found["commission_amount"] - round(found["amount"] * new_rate, 2)) < 0.011
        finally:
            admin_client.put(f"{BASE_URL}/api/sales/{sid}", json={"commission_rate": original_rate}, timeout=30)

    def test_update_commission_month_persists(self, admin_client):
        rows = admin_client.get(f"{BASE_URL}/api/commissions", timeout=30).json()
        row = rows[0]
        sid, original = row["sale_id"], row["commission_month"]
        new_month = "2026-01" if original != "2026-01" else "2026-02"
        try:
            r = admin_client.put(f"{BASE_URL}/api/sales/{sid}", json={"commission_month": new_month}, timeout=30)
            assert r.status_code == 200, r.text[:300]
            after = admin_client.get(f"{BASE_URL}/api/commissions", timeout=30).json()
            found = [x for x in after if x["sale_id"] == sid][0]
            assert found["commission_month"] == new_month
        finally:
            if original:
                admin_client.put(f"{BASE_URL}/api/sales/{sid}", json={"commission_month": original}, timeout=30)


# ---------------- Module: Monthly report PDF ----------------
class TestMonthlyReportPdf:
    def test_pdf_valid(self, admin_client):
        r = admin_client.get(f"{BASE_URL}/api/reports/monthly.pdf", params={"month": "2026-07"}, timeout=90)
        assert r.status_code == 200, f"{r.status_code}: {r.text[:300]}"
        assert "application/pdf" in r.headers.get("content-type", ""), r.headers.get("content-type")
        assert r.content[:4] == b"%PDF", r.content[:20]
        assert len(r.content) >= 1500, len(r.content)


# ---------------- Module: AI actions ----------------
class TestAIActions:
    created_sale_ids = []
    created_client_ids = []

    def test_ai_action_create_sale_flow(self, admin_client):
        msg = "Vente Kilian 5000€ 20% chez TEST_QA_Client R1 en chèque"
        r = admin_client.post(f"{BASE_URL}/api/ai/action", json={"message": msg}, timeout=120)
        assert r.status_code == 200, f"{r.status_code}: {r.text[:400]}"
        p = r.json()
        assert p["intent"] == "create_sale", p
        d = p["data"]
        assert float(d.get("amount")) == 5000.0, d
        assert abs(float(d.get("commission_rate")) - 0.20) < 1e-6, d
        assert "TEST_QA_Client" in (d.get("client_name") or ""), d
        assert not [m for m in p["missing"] if m in ("client_name",)], p["missing"]

        ex = admin_client.post(f"{BASE_URL}/api/ai/action/execute",
                               json={"intent": "create_sale", "data": d}, timeout=60)
        assert ex.status_code == 200, f"{ex.status_code}: {ex.text[:400]}"
        sale = ex.json()
        TestAIActions.created_sale_ids.append(sale["id"])
        TestAIActions.created_client_ids.append(sale["client_id"])
        assert sale["amount"] == 5000.0
        assert abs(sale["commission_rate"] - 0.20) < 1e-6

        # sale appears at top of the list
        sales = admin_client.get(f"{BASE_URL}/api/sales", timeout=30).json()
        assert sales[0]["id"] == sale["id"], "new sale not first in /api/sales"

    def test_ai_action_update_status(self, admin_client):
        r = admin_client.post(f"{BASE_URL}/api/ai/action",
                              json={"message": "La vente LEPESQUEUX chantier fini"}, timeout=120)
        assert r.status_code == 200, f"{r.status_code}: {r.text[:400]}"
        p = r.json()
        assert p["intent"] == "update_sale_status", p
        assert p["data"].get("status") == "chantier_fini", p
        # If the sale exists in DB it must be resolved (no sale_not_found)
        clients = admin_client.get(f"{BASE_URL}/api/clients", timeout=30).json()
        has_lepesqueux = any("lepesqueux" in (c.get("name") or "").lower() for c in clients)
        if has_lepesqueux:
            # BUG (~20% of runs): LLM returns bdc="LEPESQUEUX"; backend only looks up by bdc
            # (elif) so the sale is never found -> missing=["sale_not_found"].
            assert "sale_not_found" not in p["missing"], p
            # FIXED in iteration_3: key renamed from "_sale_id" (dropped by FastAPI's
            # jsonable_encoder sqlalchemy_safe) to "resolved_sale_id".
            assert p["data"].get("resolved_sale_id"), p

    def test_ai_execute_update_status_bdc_only_fallback(self, admin_client):
        """LLM sometimes puts the client name into bdc; execute must still resolve the sale."""
        sales = admin_client.get(f"{BASE_URL}/api/sales", timeout=30).json()
        target = next((s for s in sales if "lepesqueux" in (s.get("client_name") or "").lower()), None)
        if not target:
            pytest.skip("no LEPESQUEUX sale in DB")
        original_status = target.get("status")
        try:
            r = admin_client.post(f"{BASE_URL}/api/ai/action/execute",
                                  json={"intent": "update_sale_status",
                                        "data": {"bdc": "LEPESQUEUX", "status": "chantier_fini"}}, timeout=60)
            assert r.status_code == 200, (
                f"no client_name fallback when bdc lookup fails: {r.status_code} {r.text[:200]}")
        finally:
            admin_client.put(f"{BASE_URL}/api/sales/{target['id']}",
                             json={"status": original_status}, timeout=30)


def test_zz_cleanup_ai_test_data(admin_client):
    """xdist-safe cleanup: resolve TEST_QA_ data from the API, sales first then clients."""
    sales = admin_client.get(f"{BASE_URL}/api/sales", timeout=30).json()
    clients = admin_client.get(f"{BASE_URL}/api/clients", timeout=30).json()
    qa_client_ids = {c["id"] for c in clients if (c.get("name") or "").startswith("TEST_QA_Client")}
    for s in sales:
        if s["client_id"] in qa_client_ids or (s.get("client_name") or "").startswith("TEST_QA_Client"):
            admin_client.delete(f"{BASE_URL}/api/sales/{s['id']}", timeout=30)
    for cid in qa_client_ids:
        admin_client.delete(f"{BASE_URL}/api/clients/{cid}", timeout=30)
    after_clients = admin_client.get(f"{BASE_URL}/api/clients", timeout=30).json()
    after_sales = admin_client.get(f"{BASE_URL}/api/sales", timeout=30).json()
    assert not [c for c in after_clients if (c.get("name") or "").startswith("TEST_QA_Client")]
    assert not [s for s in after_sales if (s.get("client_name") or "").startswith("TEST_QA_Client")]


# ---------------- Module: Stripe ----------------
class TestStripe:
    def test_subscription_me(self, admin_client):
        r = admin_client.get(f"{BASE_URL}/api/subscription/me", timeout=30)
        assert r.status_code == 200, f"{r.status_code}: {r.text[:300]}"
        d = r.json()
        assert "plan" in d and "status" in d, d

    def test_checkout_creates_session_and_transaction(self, admin_client):
        r = admin_client.post(f"{BASE_URL}/api/payments/checkout",
                              json={"lookup_key": "keylot_medium_monthly", "origin_url": BASE_URL}, timeout=60)
        assert r.status_code == 200, f"{r.status_code}: {r.text[:400]}"
        d = r.json()
        assert d["checkout_url"].startswith("https://checkout.stripe.com/"), d["checkout_url"]
        sid = d["session_id"]
        st = admin_client.get(f"{BASE_URL}/api/payments/status/{sid}", timeout=60)
        assert st.status_code == 200, st.text[:300]
        rec = st.json()
        assert rec.get("lookup_key") == "keylot_medium_monthly", rec
        assert "_id" not in rec


# ---------------- Module: Bilan mensuel cron ----------------
class TestBilanMensuel:
    def test_bilan_test_endpoint(self, admin_client):
        r = admin_client.post(f"{BASE_URL}/api/cron/bilan-mensuel/test", timeout=120)
        assert r.status_code == 200, f"{r.status_code}: {r.text[:400]}"
        d = r.json()
        assert "month" in d, d
        assert ("sent" in d) or ("recipient" in d) or ("recipients" in d), d

    def test_bilan_requires_admin(self):
        r = requests.post(f"{BASE_URL}/api/cron/bilan-mensuel/test", timeout=30)
        assert r.status_code in (401, 403), r.status_code
