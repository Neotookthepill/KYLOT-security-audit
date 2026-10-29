"""Iteration 15 — re-validation of the 3 critical + 7 minor fixes reported in iteration 14.

Pre-requisite: run `python /app/backend/tests/_seed_prelaunch.py seed` first
(creates TEST_Alpha SARL + TEST_Beta SAS with users Théo/Léa/Sébastien/Lucas/Marc/Responsable).
"""
import os
from datetime import datetime, timedelta, timezone

import pytest
import requests
from dotenv import dotenv_values

frontend_env = dotenv_values("/app/frontend/.env")
base_url = os.environ.get("REACT_APP_BACKEND_URL") or frontend_env.get("REACT_APP_BACKEND_URL")
if not base_url:
    raise RuntimeError("REACT_APP_BACKEND_URL missing")
BASE = base_url.rstrip("/") + "/api"

TODAY = datetime.now(timezone.utc).date()
TOMORROW = (TODAY + timedelta(days=1)).isoformat()

ACCOUNTS = {
    "super": ("super@keylot.app", "Super@2026"),
    "alpha": ("alpha-admin@keylot.example.com", "Alpha@2026"),
    "beta": ("beta-admin@keylot.example.com", "Beta@2026"),
    "theo": ("theo.alpha@keylot.example.com", "Theo@2026"),
    "lea": ("lea.alpha@keylot.example.com", "Lea@2026"),
    "seb": ("seb.alpha@keylot.example.com", "Seb@2026"),
    "lucas": ("lucas.alpha@keylot.example.com", "Lucas@2026"),
    "resp": ("resp.alpha@keylot.example.com", "Resp@2026"),
}


def login(key):
    email, pwd = ACCOUNTS[key]
    r = requests.post(f"{BASE}/auth/login", json={"email": email, "password": pwd}, timeout=30)
    if r.status_code != 200:
        pytest.fail(f"login {key} failed {r.status_code}: {r.text[:300]}")
    s = requests.Session()
    s.headers.update({"Authorization": f"Bearer {r.json()['token']}", "Content-Type": "application/json"})
    return s


@pytest.fixture(scope="module")
def sessions():
    return {k: login(k) for k in ACCOUNTS}


# ---------------- CRITICAL #1: executive scoped for commercial ----------------
class TestExecutiveScopeCommercial:
    def test_lea_gets_a_sale(self, sessions):
        """Give Léa one sale so both commercials have data."""
        lea = sessions["lea"]
        c = lea.post(f"{BASE}/clients", json={"name": "TEST_Client Lea", "phone": "0611111111",
                                              "city": "Lyon", "address": "2 rue Lea", "postal_code": "69001"}, timeout=30)
        assert c.status_code in (200, 201), c.text
        s = lea.post(f"{BASE}/sales", json={"client_id": c.json()["id"], "service": "PAC", "amount": 4000,
                                            "commission_rate": 0.10, "commercial": "Léa",
                                            "sale_date": TODAY.isoformat(), "status": "commercial_cheque"}, timeout=30)
        assert s.status_code in (200, 201), s.text

    def test_admin_sees_company_total(self, sessions):
        r = sessions["alpha"].get(f"{BASE}/dashboard/executive?period=month", timeout=30)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["ca"]["total"] == pytest.approx(17000)  # 5000+8000 (Théo) + 4000 (Léa)
        assert len(d["ranking"]) == 2

    def test_commercial_theo_own_scope(self, sessions):
        r = sessions["theo"].get(f"{BASE}/dashboard/executive?period=month", timeout=30)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["ca"]["total"] == pytest.approx(13000), f"Théo must only see his own CA, got {d['ca']['total']}"
        assert d["sales"]["count"] == 2
        assert len(d["ranking"]) == 1, f"ranking must contain only Théo, got {d['ranking']}"
        assert d["ranking"][0]["commercial"] == "Théo"
        names = [(s.get("commercial") or "") for s in d.get("recent_sales", [])]
        assert all(n == "Théo" for n in names), f"recent_sales leaks other commercials: {names}"

    def test_commercial_lea_own_scope(self, sessions):
        d = sessions["lea"].get(f"{BASE}/dashboard/executive", timeout=30).json()
        assert d["ca"]["total"] == pytest.approx(4000)
        assert len(d["ranking"]) == 1 and d["ranking"][0]["commercial"] == "Léa"


# ---------------- CRITICAL #2: responsable blocked ----------------
class TestExecutiveResponsable:
    def test_responsable_forbidden(self, sessions):
        r = sessions["resp"].get(f"{BASE}/dashboard/executive", timeout=30)
        assert r.status_code == 403, f"responsable (sales.view=none) must get 403, got {r.status_code}: {r.text[:300]}"

    def test_technicien_forbidden(self, sessions):
        r = sessions["seb"].get(f"{BASE}/dashboard/executive", timeout=30)
        assert r.status_code == 403, f"technicien must get 403, got {r.status_code}"

    def test_responsable_permissions_defaults(self, sessions):
        me = sessions["resp"].get(f"{BASE}/auth/me", timeout=30).json()
        perms = me.get("permissions") or {}
        assert (perms.get("sales") or {}).get("view") in (None, "none"), perms.get("sales")


# ---------------- CRITICAL #3: technicien cannot edit unassigned project ----------------
class TestTechnicienProjectScope:
    def test_seb_cannot_edit_lucas_project(self, sessions):
        projects = sessions["alpha"].get(f"{BASE}/projects", timeout=30).json()
        lucas_p = [p for p in projects if "Lucas" in (p.get("assigned_to") or [])]
        seb_p = [p for p in projects if "Sébastien" in (p.get("assigned_to") or [])]
        assert lucas_p and seb_p, f"seed issue: assignments {[(p['id'], p.get('assigned_to')) for p in projects]}"
        r = sessions["seb"].put(f"{BASE}/projects/{lucas_p[0]['id']}", json={"status": "termine"}, timeout=30)
        assert r.status_code == 404, f"expected 404 on unassigned project, got {r.status_code}: {r.text[:300]}"
        # confirm untouched
        after = [p for p in sessions["alpha"].get(f"{BASE}/projects", timeout=30).json()
                 if p["id"] == lucas_p[0]["id"]][0]
        assert after["status"] != "termine"

    def test_seb_can_edit_own_project(self, sessions):
        projects = sessions["alpha"].get(f"{BASE}/projects", timeout=30).json()
        seb_p = [p for p in projects if "Sébastien" in (p.get("assigned_to") or [])][0]
        r = sessions["seb"].put(f"{BASE}/projects/{seb_p['id']}", json={"status": "en_cours"}, timeout=30)
        assert r.status_code == 200, r.text
        assert r.json()["status"] == "en_cours"

    def test_technicien_cannot_reassign(self, sessions):
        projects = sessions["alpha"].get(f"{BASE}/projects", timeout=30).json()
        seb_p = [p for p in projects if "Sébastien" in (p.get("assigned_to") or [])][0]
        r = sessions["seb"].put(f"{BASE}/projects/{seb_p['id']}", json={"assigned_to": ["Lucas"]}, timeout=30)
        assert r.status_code == 200, r.text
        assert "Sébastien" in (r.json().get("assigned_to") or []), "technicien managed to re-assign"


# ---------------- MINOR: Pydantic validation ----------------
class TestSaleValidation:
    @pytest.mark.parametrize("payload,label", [
        ({"service": "Isolation", "amount": -100, "sale_date": str(TODAY)}, "negative amount"),
        ({"service": "", "amount": 100, "sale_date": str(TODAY)}, "empty service"),
        ({"service": "Isolation", "amount": 100, "sale_date": "31/02/2026"}, "bad date format"),
        ({"service": "Isolation", "amount": 100, "sale_date": str(TODAY), "commission_rate": 1.5}, "rate > 1"),
        ({"service": "Isolation", "amount": 1e15, "sale_date": str(TODAY)}, "amount overflow"),
    ])
    def test_invalid_sale_rejected(self, sessions, payload, label):
        r = sessions["alpha"].post(f"{BASE}/sales", json=payload, timeout=30)
        assert r.status_code == 422, f"{label} should be 422, got {r.status_code}: {r.text[:200]}"

    def test_sale_update_validation(self, sessions):
        sale = sessions["alpha"].get(f"{BASE}/sales", timeout=30).json()[0]
        r = sessions["alpha"].put(f"{BASE}/sales/{sale['id']}", json={"amount": -1}, timeout=30)
        assert r.status_code == 422, r.text


# ---------------- MINOR: DELETE 404 ----------------
class TestDelete404:
    @pytest.mark.parametrize("path", ["sales", "projects", "clients", "users"])
    def test_delete_unknown_id_returns_404(self, sessions, path):
        r = sessions["alpha"].delete(f"{BASE}/{path}/fake-id-xyz", timeout=30)
        assert r.status_code == 404, f"DELETE /{path}/fake-id should be 404, got {r.status_code}: {r.text[:200]}"


# ---------------- MINOR: recent_sales client_name ----------------
class TestRecentSales:
    def test_client_name_present(self, sessions):
        d = sessions["alpha"].get(f"{BASE}/dashboard/executive", timeout=30).json()
        recent = d.get("recent_sales") or []
        assert recent, "no recent sales"
        withclient = [s for s in recent if s.get("client_id")]
        assert withclient, "no sale with client_id"
        for s in withclient:
            assert s.get("client_name"), f"client_name missing/empty for sale {s.get('id')}"


# ---------------- Isolation recheck ----------------
class TestIsolation:
    def test_beta_sees_no_alpha_sales(self, sessions):
        alpha_sales = sessions["alpha"].get(f"{BASE}/sales", timeout=30).json()
        assert len(alpha_sales) >= 3
        beta_sales = sessions["beta"].get(f"{BASE}/sales", timeout=30).json()
        assert len(beta_sales) == 0, f"Beta sees {len(beta_sales)} sales"
        # no GET /sales/{id} endpoint -> verify cross-company write is refused with 404
        r = sessions["beta"].put(f"{BASE}/sales/{alpha_sales[0]['id']}", json={"amount": 1}, timeout=30)
        assert r.status_code == 404, f"cross-company update returned {r.status_code}"

    def test_beta_cannot_delete_alpha_sale(self, sessions):
        alpha_sales = sessions["alpha"].get(f"{BASE}/sales", timeout=30).json()
        sid = alpha_sales[0]["id"]
        r = sessions["beta"].delete(f"{BASE}/sales/{sid}", timeout=30)
        assert r.status_code == 404, f"expected 404 got {r.status_code}"
        still = [x for x in sessions["alpha"].get(f"{BASE}/sales", timeout=30).json() if x["id"] == sid]
        assert still, "Alpha sale was deleted by Beta admin!"


# ---------------- Smoke: full journey ----------------
class TestSmokeJourney:
    def test_full_flow(self, sessions):
        theo, admin, seb = sessions["theo"], sessions["alpha"], sessions["seb"]
        c = theo.post(f"{BASE}/clients", json={"name": "TEST_Smoke Client", "phone": "0622222222",
                                               "city": "Lyon", "address": "9 rue Smoke", "postal_code": "69003"}, timeout=30)
        assert c.status_code in (200, 201), c.text
        cid = c.json()["id"]
        s = theo.post(f"{BASE}/sales", json={"client_id": cid, "service": "Isolation", "amount": 5000,
                                             "commission_rate": 0.10, "commercial": "Théo",
                                             "sale_date": TODAY.isoformat(), "status": "commercial_cheque"}, timeout=30)
        assert s.status_code in (200, 201), s.text
        sale_id = s.json()["id"]

        # auto-created project
        projects = admin.get(f"{BASE}/projects", timeout=30).json()
        proj = [p for p in projects if p.get("sale_id") == sale_id]
        assert proj, "no chantier auto-created from the sale"
        pid = proj[0]["id"]

        # admin schedules + assigns
        r = admin.put(f"{BASE}/projects/{pid}", json={"assigned_to": ["Sébastien"],
                                                      "scheduled_date": TOMORROW, "status": "en_cours"}, timeout=30)
        assert r.status_code == 200, r.text
        assert "Sébastien" in r.json()["assigned_to"]
        assert r.json()["scheduled_date"] == TOMORROW

        # technicien sees it
        seb_projects = seb.get(f"{BASE}/projects", timeout=30).json()
        assert pid in [p["id"] for p in seb_projects], "technicien does not see his assigned chantier"

        # technicien declares 2h overtime
        ot = seb.post(f"{BASE}/overtime", json={"technician_name": "Sébastien",
                                                "date": TODAY.isoformat(), "hours": 2}, timeout=30)
        assert ot.status_code in (200, 201), ot.text
        ot_id = ot.json()["id"]

        # admin approves
        appr = admin.put(f"{BASE}/overtime/{ot_id}/validate", timeout=30)
        assert appr.status_code == 200, appr.text
        assert appr.json()["status"] == "approved"

        # dashboard reflects
        d = admin.get(f"{BASE}/dashboard/executive", timeout=30).json()
        assert d["ca"]["total"] == pytest.approx(22000), d["ca"]
        assert d["sales"]["count"] == 4
        assert d["commissions"]["total"] == pytest.approx(2200), d["commissions"]

    def test_commercial_cannot_approve_overtime(self, sessions):
        month = TODAY.strftime("%Y-%m")
        data = sessions["alpha"].get(f"{BASE}/overtime?month={month}", timeout=30).json()
        entries = data.get("entries") if isinstance(data, dict) else data
        assert entries, f"no overtime entries: {data}"
        r = sessions["theo"].put(f"{BASE}/overtime/{entries[0]['id']}/validate", timeout=30)
        assert r.status_code in (403, 404), f"commercial approved overtime: {r.status_code}"
