"""Iteration 14 — Pre-launch full review (KEYLOT).

Scenario: 1 admin + 2 commerciaux + 3 techniciens in company "TEST_Alpha SARL",
plus a second company "TEST_Beta SAS" used for multi-tenant isolation checks.

Covers: commercial journey (clients -> sales -> commissions -> dashboard),
auto-created chantier, planning assignment, technician visibility, overtime
workflow (declare/validate), responsable role, executive dashboard, granular
permissions, cross-company isolation, user input errors.
"""
import os
from datetime import datetime, timedelta, timezone

import pytest
import requests
from dotenv import dotenv_values

frontend_env = dotenv_values("/app/frontend/.env")
_b = os.environ.get("REACT_APP_BACKEND_URL") or frontend_env.get("REACT_APP_BACKEND_URL")
if not _b:
    raise RuntimeError("REACT_APP_BACKEND_URL missing")
BASE = _b.rstrip("/") + "/api"

SUPER = ("super@keylot.app", "Super@2026")

ALPHA_NAME = "TEST_Alpha SARL"
BETA_NAME = "TEST_Beta SAS"
ALPHA_ADMIN = ("alpha-admin@keylot.example.com", "Alpha@2026")
BETA_ADMIN = ("beta-admin@keylot.example.com", "Beta@2026")
THEO = ("theo.alpha@keylot.example.com", "Theo@2026", "Théo")
LEA = ("lea.alpha@keylot.example.com", "Lea@2026", "Léa")
SEB = ("seb.alpha@keylot.example.com", "Seb@2026", "Sébastien")
LUCAS = ("lucas.alpha@keylot.example.com", "Lucas@2026", "Lucas")
MARC = ("marc.alpha@keylot.example.com", "Marc@2026", "Marc")
RESP = ("resp.alpha@keylot.example.com", "Resp@2026", "Responsable Alpha")

TODAY = datetime.now(timezone.utc).date()
MONTH = TODAY.strftime("%Y-%m")
TOMORROW = (TODAY + timedelta(days=1)).isoformat()
AFTER_TOMORROW = (TODAY + timedelta(days=2)).isoformat()
OT_DATE = TODAY.isoformat()

S = {}  # shared state


def sess(token):
    s = requests.Session()
    s.headers.update({"Authorization": f"Bearer {token}", "Content-Type": "application/json"})
    return s


def login(email, password):
    r = requests.post(f"{BASE}/auth/login", json={"email": email, "password": password}, timeout=30)
    if r.status_code != 200:
        pytest.fail(f"Login failed {email}: {r.status_code} {r.text[:300]}")
    return sess(r.json()["token"])


@pytest.fixture(scope="module", autouse=True)
def bootstrap():
    """Create the two test companies (cleaning leftovers first); cascade-delete at the end."""
    su = login(*SUPER)
    r = su.get(f"{BASE}/superadmin/companies", timeout=30)
    assert r.status_code == 200, r.text
    for c in r.json():
        if c["name"] in (ALPHA_NAME, BETA_NAME):
            su.delete(f"{BASE}/superadmin/companies/{c['id']}", timeout=30)
    for name, adm in ((ALPHA_NAME, ALPHA_ADMIN), (BETA_NAME, BETA_ADMIN)):
        cr = su.post(f"{BASE}/superadmin/companies", json={
            "name": name, "admin_email": adm[0], "admin_password": adm[1], "admin_name": name + " Admin",
        }, timeout=30)
        assert cr.status_code == 200, f"create company {name}: {cr.status_code} {cr.text[:300]}"
        S[name] = cr.json()["company"]["id"]
    S["super"] = su
    yield
    for name in (ALPHA_NAME, BETA_NAME):
        if S.get(name):
            su.delete(f"{BASE}/superadmin/companies/{S[name]}", timeout=30)


class TestPrelaunch:
    # ---------- SETUP / isolation at creation ----------
    def test_01_fresh_company_is_empty(self):
        a = login(*ALPHA_ADMIN)
        S["a"] = a
        me = a.get(f"{BASE}/auth/me", timeout=30).json()
        assert me["company_id"] == S[ALPHA_NAME]
        assert me["role"] == "admin"
        assert me.get("permissions")
        for path, expected in (("/sales", 0), ("/clients", 0), ("/projects", 0), ("/team", 0)):
            r = a.get(f"{BASE}{path}", timeout=30)
            assert r.status_code == 200, f"{path} -> {r.status_code}"
            assert len(r.json()) == expected, f"{path} should be empty, got {len(r.json())}"
        users = a.get(f"{BASE}/users", timeout=30).json()
        assert len(users) == 1 and users[0]["email"] == ALPHA_ADMIN[0]

    def test_02_create_alpha_team(self):
        a = S["a"]
        for email, pwd, name, role in (
            (*THEO, "commercial"), (*LEA, "commercial"),
            (*SEB, "technicien"), (*LUCAS, "technicien"), (*MARC, "technicien"),
            (*RESP, "responsable"),
        ):
            r = a.post(f"{BASE}/users", json={"email": email, "password": pwd, "name": name, "role": role}, timeout=30)
            assert r.status_code == 200, f"create {email}: {r.status_code} {r.text[:200]}"
            S[f"uid_{name}"] = r.json()["id"]
            assert r.json()["role"] == role
        for name, t in ((THEO[2], "commercial"), (LEA[2], "commercial"),
                        (SEB[2], "technicien"), (LUCAS[2], "technicien"), (MARC[2], "technicien")):
            r = a.post(f"{BASE}/team", json={"name": name, "type": t, "objectif": 20000}, timeout=30)
            assert r.status_code == 200, f"team {name}: {r.status_code} {r.text[:200]}"
        assert len(a.get(f"{BASE}/users", timeout=30).json()) == 7
        assert len(a.get(f"{BASE}/team", timeout=30).json()) == 5

    # ---------- Commercial journey ----------
    def test_03_theo_creates_clients_and_sales(self):
        t = login(THEO[0], THEO[1])
        S["theo"] = t
        for cname in ("Dupont", "Martin"):
            r = t.post(f"{BASE}/clients", json={"name": cname, "phone": "0600000000", "city": "Lyon"}, timeout=30)
            assert r.status_code == 200, r.text
            S[f"client_{cname}"] = r.json()["id"]
        for cname, amount in (("Dupont", 5000), ("Martin", 8000)):
            r = t.post(f"{BASE}/sales", json={
                "client_id": S[f"client_{cname}"], "service": "Isolation", "amount": amount,
                "commission_rate": 0.10, "commercial": THEO[2], "sale_date": TODAY.isoformat(),
                "status": "commercial_cheque",
            }, timeout=30)
            assert r.status_code == 200, f"sale {cname}: {r.status_code} {r.text[:300]}"
            S[f"sale_{cname}"] = r.json()["id"]
            assert r.json()["amount"] == amount

    def test_04_theo_sees_only_own_data(self):
        t = S["theo"]
        sales = t.get(f"{BASE}/sales", timeout=30).json()
        assert len(sales) == 2, f"Théo should see 2 sales, got {len(sales)}"
        clients = t.get(f"{BASE}/clients", timeout=30).json()
        assert len(clients) == 2
        comms = t.get(f"{BASE}/commissions", timeout=30).json()
        assert sorted(c["commission_amount"] for c in comms) == [500.0, 800.0]
        stats = t.get(f"{BASE}/dashboard/stats", timeout=30).json()
        assert stats["ca_total"] == 13000.0, stats
        assert stats["sales_count"] == 2

    def test_05_lea_sees_nothing(self):
        lea = login(LEA[0], LEA[1])
        S["lea"] = lea
        assert lea.get(f"{BASE}/sales", timeout=30).json() == []
        assert lea.get(f"{BASE}/clients", timeout=30).json() == []
        assert lea.get(f"{BASE}/commissions", timeout=30).json() == []
        assert lea.get(f"{BASE}/dashboard/stats", timeout=30).json()["ca_total"] == 0
        # commercial has no overtime / users access
        assert lea.get(f"{BASE}/overtime?month={MONTH}", timeout=30).status_code == 403
        assert lea.get(f"{BASE}/users", timeout=30).status_code == 403

    def test_06_projects_auto_created(self):
        a = S["a"]
        projects = a.get(f"{BASE}/projects", timeout=30).json()
        assert len(projects) == 2, f"expected 2 auto-created chantiers, got {len(projects)}"
        assert all(p["status"] == "a_planifier" for p in projects), projects
        for p in projects:
            S[f"proj_{p['client_name']}"] = p["id"]
        assert S.get("proj_Dupont") and S.get("proj_Martin")

    def test_07_admin_plans_projects(self):
        a = S["a"]
        for cname, tech, date in (("Dupont", SEB[2], TOMORROW), ("Martin", LUCAS[2], AFTER_TOMORROW)):
            r = a.put(f"{BASE}/projects/{S['proj_' + cname]}", json={
                "assigned_to": [tech], "scheduled_date": date, "status": "en_cours",
            }, timeout=30)
            assert r.status_code == 200, r.text
            assert r.json()["assigned_to"] == [tech]
            assert r.json()["scheduled_date"] == date

    def test_08_commercial_planning_visibility(self):
        projects = S["theo"].get(f"{BASE}/projects", timeout=30).json()
        assert len(projects) == 2, f"Théo should see his 2 chantiers, got {len(projects)}"
        assert S["lea"].get(f"{BASE}/projects", timeout=30).json() == []

    def test_09_technician_visibility(self):
        seb = login(SEB[0], SEB[1])
        S["seb"] = seb
        projects = seb.get(f"{BASE}/projects", timeout=30).json()
        assert len(projects) == 1, f"Sébastien should see only Dupont, got {[p.get('client_name') for p in projects]}"
        p = projects[0]
        assert p["client_name"] == "Dupont"
        assert "amount" not in p and "commission_rate" not in p, f"financial leak in project payload: {p.keys()}"
        assert seb.get(f"{BASE}/sales", timeout=30).status_code == 403
        assert seb.get(f"{BASE}/clients", timeout=30).status_code == 403
        assert seb.get(f"{BASE}/commissions", timeout=30).status_code == 403
        assert seb.get(f"{BASE}/dashboard/stats", timeout=30).status_code == 403
        assert seb.get(f"{BASE}/dashboard/executive?period=month", timeout=30).status_code == 403

    # ---------- Overtime ----------
    def test_10_technician_declares_overtime(self):
        seb = S["seb"]
        r = seb.post(f"{BASE}/overtime", json={"technician_name": SEB[2], "date": OT_DATE, "hours": 2}, timeout=30)
        assert r.status_code == 200, r.text
        S["ot_id"] = r.json()["id"]
        assert r.json()["status"] == "pending" and r.json()["hours"] == 2
        # cannot declare for someone else
        r2 = seb.post(f"{BASE}/overtime", json={"technician_name": LUCAS[2], "date": OT_DATE, "hours": 5}, timeout=30)
        assert r2.status_code == 403, f"expected 403, got {r2.status_code} {r2.text[:200]}"
        # invalid date
        r3 = seb.post(f"{BASE}/overtime", json={"technician_name": SEB[2], "date": "2026-13-45", "hours": 1}, timeout=30)
        assert r3.status_code == 400, f"invalid date -> {r3.status_code}"
        # negative hours rejected by model
        r4 = seb.post(f"{BASE}/overtime", json={"technician_name": SEB[2], "date": OT_DATE, "hours": -3}, timeout=30)
        assert r4.status_code == 422, f"negative hours -> {r4.status_code}"
        # technician sees only own entries
        data = seb.get(f"{BASE}/overtime?month={MONTH}", timeout=30).json()
        assert all(e["technician_name"] == SEB[2] for e in data["entries"])
        # technician cannot validate own hours
        assert seb.put(f"{BASE}/overtime/{S['ot_id']}/validate", timeout=30).status_code == 403
        assert seb.post(f"{BASE}/overtime/validate-tech", json={"technician_name": SEB[2], "month": MONTH}, timeout=30).status_code == 403

    def test_11_admin_validates_overtime(self):
        a = S["a"]
        data = a.get(f"{BASE}/overtime?month={MONTH}", timeout=30).json()
        entry = next((e for e in data["entries"] if e["id"] == S["ot_id"]), None)
        assert entry and entry["status"] == "pending", data
        r = a.put(f"{BASE}/overtime/{S['ot_id']}/validate", timeout=30)
        assert r.status_code == 200 and r.json()["status"] == "approved", r.text
        again = a.get(f"{BASE}/overtime?month={MONTH}", timeout=30).json()
        row = next(x for x in again["rows"] if x["technician_name"] == SEB[2])
        assert row["approved_hours"] == 2 and row["pending_hours"] == 0, row

    def test_12_responsable_role(self):
        resp = login(RESP[0], RESP[1])
        S["resp"] = resp
        # can view/validate overtime
        assert resp.get(f"{BASE}/overtime?month={MONTH}", timeout=30).status_code == 200
        S["seb"].post(f"{BASE}/overtime", json={"technician_name": SEB[2], "date": TOMORROW, "hours": 3}, timeout=30)
        r = resp.post(f"{BASE}/overtime/validate-tech", json={"technician_name": SEB[2], "month": MONTH}, timeout=30)
        assert r.status_code == 200 and r.json()["validated"] >= 1, r.text
        # no financials
        assert resp.get(f"{BASE}/commissions", timeout=30).status_code == 403
        assert resp.get(f"{BASE}/sales", timeout=30).status_code == 403
        assert resp.get(f"{BASE}/users", timeout=30).status_code == 403
        assert resp.get(f"{BASE}/projects", timeout=30).status_code == 200

    # ---------- Dashboards ----------
    def test_13_executive_dashboard(self):
        d = S["a"].get(f"{BASE}/dashboard/executive?period=month", timeout=30)
        assert d.status_code == 200, d.text
        j = d.json()
        blob = str(j)
        assert 13000 in _numbers(j), f"CA 13000 missing from executive dashboard: {blob[:600]}"
        assert 1300 in _numbers(j) or 1300.0 in _numbers(j), f"commissions 1300 missing: {blob[:600]}"
        # overtime validated hours (2 + 3 = 5)
        assert any(k for k in _flat_keys(j) if "overtime" in k or "heures" in k), f"no overtime block: {list(_flat_keys(j))}"
        S["exec_month"] = j

    def test_14_executive_ranking(self):
        j = S["exec_month"]
        rank = None
        for v in j.values():
            if isinstance(v, list) and v and isinstance(v[0], dict) and any("commercial" in k or "name" in k for k in v[0]):
                rank = v
                break
        assert rank, f"no ranking list in executive payload: {list(j.keys())}"
        top = rank[0]
        assert THEO[2] in str(top), f"Théo should be first in ranking, got {top}"

    # ---------- CRITICAL: cross-company isolation ----------
    def test_15_beta_cannot_read_alpha(self):
        b = login(*BETA_ADMIN)
        S["b"] = b
        assert b.get(f"{BASE}/projects", timeout=30).json() == []
        assert b.get(f"{BASE}/clients", timeout=30).json() == []
        assert b.get(f"{BASE}/sales", timeout=30).json() == []
        assert b.get(f"{BASE}/team", timeout=30).json() == []
        users = b.get(f"{BASE}/users", timeout=30).json()
        assert len(users) == 1 and users[0]["email"] == BETA_ADMIN[0], users
        assert b.get(f"{BASE}/dashboard/stats", timeout=30).json()["ca_total"] == 0
        ot = b.get(f"{BASE}/overtime?month={MONTH}", timeout=30).json()
        assert ot["entries"] == [] and ot["grand_total"] == 0, ot

    def test_16_beta_cannot_write_alpha(self):
        b = S["b"]
        leaks = []
        checks = [
            ("PUT sale", b.put(f"{BASE}/sales/{S['sale_Dupont']}", json={"status": "annule"}, timeout=30)),
            ("DELETE sale", b.delete(f"{BASE}/sales/{S['sale_Dupont']}", timeout=30)),
            ("PUT project", b.put(f"{BASE}/projects/{S['proj_Dupont']}", json={"status": "termine"}, timeout=30)),
            ("DELETE project", b.delete(f"{BASE}/projects/{S['proj_Dupont']}", timeout=30)),
            ("PUT user", b.put(f"{BASE}/users/{S['uid_' + THEO[2]]}", json={"name": "hacked"}, timeout=30)),
            ("DELETE user", b.delete(f"{BASE}/users/{S['uid_' + THEO[2]]}", timeout=30)),
            ("PUT client", b.put(f"{BASE}/clients/{S['client_Dupont']}", json={"name": "hacked"}, timeout=30)),
            ("DELETE client", b.delete(f"{BASE}/clients/{S['client_Dupont']}", timeout=30)),
            ("PUT perms", b.put(f"{BASE}/users/{S['uid_' + THEO[2]]}/permissions", json={"permissions": {}}, timeout=30)),
            ("GET perms", b.get(f"{BASE}/users/{S['uid_' + THEO[2]]}/permissions", timeout=30)),
            ("PUT overtime validate", b.put(f"{BASE}/overtime/{S['ot_id']}/validate", timeout=30)),
        ]
        for label, r in checks:
            if r.status_code not in (403, 404):
                leaks.append(f"{label} -> {r.status_code} {r.text[:120]}")
        # Verify Alpha data untouched regardless of status codes
        a = S["a"]
        sale = next((s for s in a.get(f"{BASE}/sales", timeout=30).json() if s["id"] == S["sale_Dupont"]), None)
        assert sale is not None, "CRITICAL: Alpha sale was deleted by Beta admin"
        assert sale["status"] == "commercial_cheque", "CRITICAL: Alpha sale mutated by Beta admin"
        proj = next((p for p in a.get(f"{BASE}/projects", timeout=30).json() if p["id"] == S["proj_Dupont"]), None)
        assert proj is not None and proj["status"] == "en_cours", "CRITICAL: Alpha project mutated/deleted by Beta"
        theo = next((u for u in a.get(f"{BASE}/users", timeout=30).json() if u["id"] == S["uid_" + THEO[2]]), None)
        assert theo is not None and theo["name"] == THEO[2], "CRITICAL: Alpha user mutated/deleted by Beta"
        client = next((c for c in a.get(f"{BASE}/clients", timeout=30).json() if c["id"] == S["client_Dupont"]), None)
        assert client is not None and client["name"] == "Dupont", "CRITICAL: Alpha client mutated/deleted by Beta"
        assert not leaks, "Non-403/404 responses on cross-company writes: " + "; ".join(leaks)

    def test_17_settings_isolation(self):
        a, b = S["a"], S["b"]
        a.put(f"{BASE}/settings", json={"objectif_ca": 111111, "app_name": "ALPHA_APP"}, timeout=30)
        r = b.put(f"{BASE}/settings", json={"objectif_ca": 999, "app_name": "BETA_APP"}, timeout=30)
        assert r.status_code == 200, r.text
        sa = a.get(f"{BASE}/settings", timeout=30).json()
        sb = b.get(f"{BASE}/settings", timeout=30).json()
        assert sa["objectif_ca"] == 111111 and sa.get("app_name") == "ALPHA_APP", sa
        assert sb["objectif_ca"] == 999 and sb.get("app_name") == "BETA_APP", sb

    def test_18_beta_not_superadmin(self):
        b = S["b"]
        assert b.get(f"{BASE}/superadmin/companies", timeout=30).status_code == 403
        assert b.post(f"{BASE}/superadmin/companies", json={"name": "TEST_Hack"}, timeout=30).status_code == 403
        assert b.delete(f"{BASE}/superadmin/companies/{S[ALPHA_NAME]}", timeout=30).status_code == 403
        assert S[ALPHA_NAME] in [c["id"] for c in S["super"].get(f"{BASE}/superadmin/companies", timeout=30).json()]

    # ---------- Granular permissions ----------
    def test_19_custom_permissions_revoke_and_restore(self):
        a = S["a"]
        tid = S["uid_" + THEO[2]]
        base = a.get(f"{BASE}/users/{tid}/permissions", timeout=30).json()["permissions"]
        revoked = {**base, "sales": {**base["sales"], "create": False}}
        r = a.put(f"{BASE}/users/{tid}/permissions", json={"permissions": revoked}, timeout=30)
        assert r.status_code == 200, r.text
        t2 = login(THEO[0], THEO[1])
        cr = t2.post(f"{BASE}/sales", json={
            "client_id": S["client_Dupont"], "service": "X", "amount": 100,
            "commercial": THEO[2], "sale_date": TODAY.isoformat(),
        }, timeout=30)
        assert cr.status_code == 403, f"revoked sales.create should 403, got {cr.status_code}"
        # restore
        a.put(f"{BASE}/users/{tid}/permissions", json={"permissions": base}, timeout=30)
        t3 = login(THEO[0], THEO[1])
        assert t3.get(f"{BASE}/sales", timeout=30).status_code == 200

    # ---------- User errors / auth hardening ----------
    def test_20_user_input_errors(self):
        t = S["theo"]
        # missing client
        r = t.post(f"{BASE}/sales", json={"service": "Isolation", "amount": 100, "sale_date": TODAY.isoformat()}, timeout=30)
        assert r.status_code in (400, 422), f"sale without client -> {r.status_code} {r.text[:200]}"
        # non-numeric amount
        r2 = t.post(f"{BASE}/sales", json={
            "client_id": S["client_Dupont"], "service": "X", "amount": "abc", "sale_date": TODAY.isoformat(),
        }, timeout=30)
        assert r2.status_code == 422, f"non-numeric amount -> {r2.status_code}"
        # negative amount (business validation)
        r3 = t.post(f"{BASE}/sales", json={
            "client_id": S["client_Dupont"], "service": "X", "amount": -5000,
            "commercial": THEO[2], "sale_date": TODAY.isoformat(),
        }, timeout=30)
        if r3.status_code == 200:
            S["neg_sale_id"] = r3.json()["id"]
        assert r3.status_code in (400, 422), f"negative amount accepted ({r3.status_code}) — no server-side validation"

    def test_21_auth_hardening(self):
        # invalid token
        bad = sess("not-a-real-token")
        assert bad.get(f"{BASE}/sales", timeout=30).status_code == 401
        # no token
        assert requests.get(f"{BASE}/sales", timeout=30).status_code == 401
        # deleted user token becomes invalid
        a = S["a"]
        cu = a.post(f"{BASE}/users", json={
            "email": "tmp.alpha@keylot.example.com", "password": "Tmp@2026", "name": "TEST_Tmp", "role": "commercial",
        }, timeout=30)
        assert cu.status_code == 200, cu.text
        tmp = login("tmp.alpha@keylot.example.com", "Tmp@2026")
        assert a.delete(f"{BASE}/users/{cu.json()['id']}", timeout=30).status_code == 200
        assert tmp.get(f"{BASE}/sales", timeout=30).status_code == 401
        # wrong password
        assert requests.post(f"{BASE}/auth/login", json={"email": ALPHA_ADMIN[0], "password": "nope"}, timeout=30).status_code in (401, 429)

    # ---------- Dashboard dynamic recomputation ----------
    def test_22_cancel_sale_updates_dashboard(self):
        a = S["a"]
        if S.get("neg_sale_id"):
            a.delete(f"{BASE}/sales/{S['neg_sale_id']}", timeout=30)
        before = a.get(f"{BASE}/dashboard/stats", timeout=30).json()["ca_total"]
        r = a.put(f"{BASE}/sales/{S['sale_Martin']}", json={"status": "annule"}, timeout=30)
        assert r.status_code == 200, r.text
        after = a.get(f"{BASE}/dashboard/stats", timeout=30).json()["ca_total"]
        assert after == before - 8000, f"CA should drop by 8000: {before} -> {after}"
        ex = a.get(f"{BASE}/dashboard/executive?period=month", timeout=30).json()
        assert 13000 not in _numbers(ex), "cancelled sale still counted in executive dashboard"
        # restore
        a.put(f"{BASE}/sales/{S['sale_Martin']}", json={"status": "commercial_cheque"}, timeout=30)
        assert a.get(f"{BASE}/dashboard/stats", timeout=30).json()["ca_total"] == before


    # ---------- Intra-company scope gaps (found in iteration 14) ----------
    def test_23_executive_dashboard_respects_commercial_scope(self):
        """A commercial with sales.view='own' must not see company-wide CA/ranking."""
        lea = S["lea"]
        c = lea.post(f"{BASE}/clients", json={"name": "TEST_LeaClient"}, timeout=30).json()
        r = lea.post(f"{BASE}/sales", json={
            "client_id": c["id"], "service": "Pompe", "amount": 20000, "commission_rate": 0.2,
            "commercial": LEA[2], "sale_date": TODAY.isoformat(),
        }, timeout=30)
        assert r.status_code == 200, r.text
        ex = S["theo"].get(f"{BASE}/dashboard/executive?period=month", timeout=30).json()
        assert ex["ca"]["total"] == 13000.0, f"LEAK: Théo sees company-wide CA {ex['ca']['total']} instead of 13000"
        assert [x["commercial"] for x in ex["ranking"]] == [THEO[2]], f"LEAK: ranking exposes other commercials: {ex['ranking']}"
        assert all((s.get("commercial") or "") == THEO[2] for s in ex["recent_sales"]), \
            f"LEAK: recent_sales contains other commercials: {[s.get('commercial') for s in ex['recent_sales']]}"

    def test_24_executive_dashboard_denied_for_responsable(self):
        """responsable has sales.view='none' + commissions.view='none' -> must not read financials."""
        r = S["resp"].get(f"{BASE}/dashboard/executive?period=month", timeout=30)
        assert r.status_code == 403, f"LEAK: responsable reads financial dashboard (CA={r.json().get('ca')})"

    def test_25_technician_cannot_edit_unassigned_project(self):
        r = S["seb"].put(f"{BASE}/projects/{S['proj_Martin']}", json={"status": "termine"}, timeout=30)
        assert r.status_code in (403, 404), \
            f"Technician edited a chantier not assigned to him ({r.status_code})"

    def test_26_sale_field_validation(self):
        t = S["theo"]
        cid = S["client_Dupont"]
        r1 = t.post(f"{BASE}/sales", json={"client_id": cid, "service": "", "amount": 100, "sale_date": TODAY.isoformat(), "commercial": THEO[2]}, timeout=30)
        r2 = t.post(f"{BASE}/sales", json={"client_id": cid, "service": "x", "amount": 100, "sale_date": "31/02/2026", "commercial": THEO[2]}, timeout=30)
        r3 = t.post(f"{BASE}/sales", json={"client_id": cid, "service": "x", "amount": 1e15, "sale_date": TODAY.isoformat(), "commercial": THEO[2]}, timeout=30)
        bad = []
        if r1.status_code == 200:
            bad.append("empty service accepted")
        if r2.status_code == 200:
            bad.append("invalid sale_date format accepted")
        if r3.status_code == 200:
            bad.append("absurd amount 1e15 accepted")
        assert not bad, "; ".join(bad)

    def test_27_recent_sales_expose_client_name(self):
        ex = S["a"].get(f"{BASE}/dashboard/executive?period=month", timeout=30).json()
        assert ex["recent_sales"], "no recent sales"
        assert all(s.get("client_name") for s in ex["recent_sales"]), \
            "recent_sales lack client_name -> dashboard 'Ventes récentes' shows '—'"


def _numbers(obj, out=None):
    out = out if out is not None else set()
    if isinstance(obj, dict):
        for v in obj.values():
            _numbers(v, out)
    elif isinstance(obj, list):
        for v in obj:
            _numbers(v, out)
    elif isinstance(obj, (int, float)) and not isinstance(obj, bool):
        out.add(round(float(obj), 2))
    return out


def _flat_keys(obj, prefix="", out=None):
    out = out if out is not None else set()
    if isinstance(obj, dict):
        for k, v in obj.items():
            out.add(f"{prefix}{k}")
            _flat_keys(v, f"{prefix}{k}.", out)
    elif isinstance(obj, list):
        for v in obj:
            _flat_keys(v, prefix, out)
    return out
