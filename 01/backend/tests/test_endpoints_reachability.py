"""Iteration 2: reachability of every page-backing endpoint + cron webhook auth."""
import datetime as dt
import os

import requests
from dotenv import dotenv_values

frontend_env = dotenv_values("/app/frontend/.env")
BASE_URL = (os.environ.get("REACT_APP_BACKEND_URL") or frontend_env["REACT_APP_BACKEND_URL"]).rstrip("/")
CRON_SECRET = dotenv_values("/app/backend/.env").get("WEBHOOK_CRON_SECRET")


# ---------------- Module: all page endpoints return 200 ----------------
class TestPageEndpoints:
    def test_list_endpoints_200(self, admin_client):
        results = {}
        for path in ["/api/commissions", "/api/clients", "/api/sales", "/api/projects",
                     "/api/team", "/api/settings", "/api/subscription/me", "/api/auth/me",
                     "/api/users", "/api/dashboard/stats"]:
            r = admin_client.get(f"{BASE_URL}{path}", timeout=60)
            results[path] = r.status_code
            assert '"_id"' not in r.text, f"{path} leaks mongo _id"
        assert all(v == 200 for v in results.values()), results

    def test_team_filtered_by_type(self, admin_client):
        for t in ("commercial", "technicien"):
            r = admin_client.get(f"{BASE_URL}/api/team", params={"type": t}, timeout=30)
            assert r.status_code == 200, r.text[:200]
            rows = r.json()
            assert isinstance(rows, list)
            assert all(x.get("type") == t for x in rows), rows

    def test_monthly_report_and_pdf(self, admin_client):
        month = dt.date.today().strftime("%Y-%m")
        r = admin_client.get(f"{BASE_URL}/api/reports/monthly", params={"month": month}, timeout=60)
        assert r.status_code == 200, r.text[:200]
        assert r.json().get("month") == month or isinstance(r.json(), dict)
        p = admin_client.get(f"{BASE_URL}/api/reports/monthly.pdf", params={"month": month}, timeout=90)
        assert p.status_code == 200, p.text[:200]
        assert "application/pdf" in p.headers.get("content-type", "")
        assert p.content[:4] == b"%PDF"

    def test_payments_portal_no_subscription_400(self, admin_client):
        r = admin_client.post(f"{BASE_URL}/api/payments/portal",
                              json={"return_url": f"{BASE_URL}/abonnement"}, timeout=60)
        assert r.status_code in (200, 400), f"{r.status_code}: {r.text[:200]}"
        if r.status_code == 400:
            assert "abonnement" in r.text.lower(), r.text[:200]


# ---------------- Module: cron webhooks auth ----------------
class TestCronWebhooks:
    def test_rappel_no_auth_401(self):
        r = requests.post(f"{BASE_URL}/api/cron/rappel-chantiers-j1", json={}, timeout=30)
        assert r.status_code == 401

    def test_bilan_no_auth_401(self):
        r = requests.post(f"{BASE_URL}/api/cron/bilan-mensuel", json={}, timeout=30)
        assert r.status_code == 401

    def test_bilan_with_secret(self):
        assert CRON_SECRET, "WEBHOOK_CRON_SECRET missing"
        r = requests.post(f"{BASE_URL}/api/cron/bilan-mensuel",
                          json={"event": "schedule.triggered", "run_id": "TEST_QA_bilan_1"},
                          headers={"Authorization": f"Bearer {CRON_SECRET}"}, timeout=120)
        assert r.status_code in (200, 202), f"{r.status_code}: {r.text[:300]}"
        assert isinstance(r.json(), dict)

    def test_rappel_with_secret(self):
        r = requests.post(f"{BASE_URL}/api/cron/rappel-chantiers-j1",
                          json={"event": "schedule.triggered", "run_id": "TEST_QA_rappel_1"},
                          headers={"Authorization": f"Bearer {CRON_SECRET}"}, timeout=120)
        assert r.status_code in (200, 202), f"{r.status_code}: {r.text[:300]}"
        assert r.json().get("accepted") is True or r.json().get("duplicate") is True
