"""Iteration 3: AI update_sale_status reliability (5 consecutive calls) + create_sale regression + route audit."""
import os

import pytest
import requests
from dotenv import dotenv_values

BASE_URL = (os.environ.get("REACT_APP_BACKEND_URL") or dotenv_values("/app/frontend/.env")["REACT_APP_BACKEND_URL"]).rstrip("/")


# ---------------- Module: AI update_sale_status ----------------
class TestAiUpdateSaleStatus:
    def test_preview_resolves_sale_5_times(self, admin_client):
        failures = []
        previews = []
        for i in range(5):
            r = admin_client.post(f"{BASE_URL}/api/ai/action",
                                  json={"message": "La vente LEPESQUEUX chantier fini"}, timeout=120)
            if r.status_code != 200:
                failures.append(f"call{i}: HTTP {r.status_code} {r.text[:200]}")
                continue
            j = r.json()
            previews.append(j)
            if j.get("intent") != "update_sale_status":
                failures.append(f"call{i}: intent={j.get('intent')} data={j.get('data')}")
            if "sale_not_found" in (j.get("missing") or []):
                failures.append(f"call{i}: sale_not_found, data={j.get('data')}")
            if not (j.get("data") or {}).get("resolved_sale_id"):
                failures.append(f"call{i}: no resolved_sale_id, data={j.get('data')}")
            if (j.get("data") or {}).get("status") != "chantier_fini":
                failures.append(f"call{i}: status={(j.get('data') or {}).get('status')}")
        assert not failures, f"{len(failures)}/5 failed: {failures}"

    def test_execute_updates_status(self, admin_client):
        r = admin_client.post(f"{BASE_URL}/api/ai/action",
                              json={"message": "La vente LEPESQUEUX chantier fini"}, timeout=120)
        assert r.status_code == 200, r.text[:300]
        data = r.json().get("data") or {}
        sale_id = data.get("resolved_sale_id")
        assert sale_id, f"preview did not resolve: {r.json()}"
        original = admin_client.get(f"{BASE_URL}/api/sales", timeout=60).json()
        prev_status = [s for s in original if s["id"] == sale_id][0]["status"]
        try:
            ex = admin_client.post(f"{BASE_URL}/api/ai/action/execute",
                                   json={"intent": "update_sale_status", "data": data}, timeout=120)
            assert ex.status_code == 200, f"{ex.status_code}: {ex.text[:300]}"
            assert ex.json().get("status") == "chantier_fini", ex.json()
            after = admin_client.get(f"{BASE_URL}/api/sales", timeout=60).json()
            assert [s for s in after if s["id"] == sale_id][0]["status"] == "chantier_fini"
        finally:
            admin_client.put(f"{BASE_URL}/api/sales/{sale_id}", json={"status": prev_status}, timeout=60)

    def test_unresolvable_sale_reports_sale_not_found(self, admin_client):
        r = admin_client.post(f"{BASE_URL}/api/ai/action",
                              json={"message": "La vente ZZZINCONNUQA9999 chantier fini"}, timeout=120)
        assert r.status_code == 200, r.text[:300]
        j = r.json()
        assert j.get("intent") == "update_sale_status", j
        assert "sale_not_found" in (j.get("missing") or []), j


# ---------------- Module: AI create_sale regression ----------------
class TestAiCreateSale:
    def test_create_sale_preview_and_execute(self, admin_client):
        r = admin_client.post(f"{BASE_URL}/api/ai/action",
                              json={"message": "Vente Kilian 5000€ 20% chez TestQA R3 chèque"}, timeout=120)
        assert r.status_code == 200, r.text[:300]
        j = r.json()
        assert j.get("intent") == "create_sale", j
        assert j.get("missing") == [], j
        sale_id = None
        client_id = None
        try:
            ex = admin_client.post(f"{BASE_URL}/api/ai/action/execute",
                                   json={"intent": "create_sale", "data": j["data"]}, timeout=120)
            assert ex.status_code == 200, f"{ex.status_code}: {ex.text[:300]}"
            sale = ex.json()
            sale_id = sale.get("id")
            client_id = sale.get("client_id")
            assert float(sale.get("amount")) == 5000.0, sale
            assert float(sale.get("commission_rate")) == 0.2, sale
        finally:
            if sale_id:
                admin_client.delete(f"{BASE_URL}/api/sales/{sale_id}", timeout=60)
            if client_id:
                admin_client.delete(f"{BASE_URL}/api/clients/{client_id}", timeout=60)


# ---------------- Module: endpoint audit (no missing decorators) ----------------
AUDIT = [
    ("POST", "/api/auth/login", (200, 400, 401, 422)),
    ("GET", "/api/auth/me", (401, 403)),
    ("GET", "/api/clients", (401, 403)),
    ("GET", "/api/sales", (401, 403)),
    ("GET", "/api/projects", (401, 403)),
    ("GET", "/api/team", (401, 403)),
    ("GET", "/api/settings", (401, 403)),
    ("GET", "/api/commissions", (401, 403)),
    ("GET", "/api/reports/monthly", (401, 403, 422)),
    ("GET", "/api/reports/monthly.pdf", (401, 403, 422)),
    ("POST", "/api/ai/chat", (401, 403, 422)),
    ("POST", "/api/ai/action", (401, 403, 422)),
    ("POST", "/api/ai/action/execute", (401, 403, 422)),
    ("POST", "/api/payments/checkout", (401, 403, 422)),
    ("GET", "/api/payments/status/sid_dummy_qa", (200, 400, 401, 403, 404, 500)),
    ("POST", "/api/payments/portal", (401, 403, 422)),
    ("GET", "/api/subscription/me", (401, 403)),
    ("POST", "/api/stripe/webhook", (400, 401, 403, 422, 500)),
    ("POST", "/api/cron/rappel-chantiers-j1", (401, 403)),
    ("POST", "/api/cron/rappel-chantiers-j1/test", (401, 403)),
    ("POST", "/api/cron/bilan-mensuel", (401, 403)),
    ("POST", "/api/cron/bilan-mensuel/test", (401, 403)),
]


class TestEndpointAudit:
    def test_no_endpoint_returns_404(self):
        bad = {}
        for method, path, expected in AUDIT:
            r = requests.request(method, f"{BASE_URL}{path}", json={}, timeout=60)
            # a 404 with FastAPI's default body means the route/decorator is missing
            if r.status_code == 404 and '"Not Found"' in r.text:
                bad[f"{method} {path}"] = "ROUTE MISSING (404 Not Found)"
                continue
            if r.status_code not in expected:
                bad[f"{method} {path}"] = f"{r.status_code} {r.text[:120]}"
        assert not bad, bad
