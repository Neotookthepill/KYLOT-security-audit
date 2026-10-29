"""iter25/27/28/29 backend validation + regression on critical endpoints.

Covers:
- K8s probes: GET /health, /healthz (no auth)
- Auth: POST /api/auth/login (all roles), /api/auth/logout token revocation
- iter28 commercial bonuses: /api/bonuses CRUD + /api/bonuses/progress + RBAC + tenant isolation
- iter29 technician project bonuses: /api/projects/{pid}/bonuses, /api/project-bonuses/*
- iter25 AI corrections: /api/ai/corrections POST/GET/DELETE + RBAC
- iter27 flexible commissions: fixed vs evolutive_ca via GET /api/commissions
- iter23 project notes: GET/PUT/DELETE /api/projects/{pid}/notes
- Regression: GET/POST/PUT /api/sales
"""
import os
import uuid

import pytest
import requests
from dotenv import dotenv_values

frontend_env = dotenv_values("/app/frontend/.env")
_base = os.environ.get("REACT_APP_BACKEND_URL") or frontend_env.get("REACT_APP_BACKEND_URL")
if not _base:
    raise RuntimeError("REACT_APP_BACKEND_URL missing")
BASE = _base.rstrip("/")
API = f"{BASE}/api"

ADMIN = ("admin@example.invalid", "CHANGE_ME_TEST_PASSWORD")
COMM = ("comm-perms@keylot.app", "Comm@2026")
RESP = ("resp-perms@keylot.app", "Resp@2026")
TECH1 = ("test-tech@keylot.app", "Tech@2026")
TECH2 = ("test-tech2@keylot.app", "Tech@2026")
ACME = ("boss@acme.example.com", "Acme@2026")

TECH1_NAME = "TEST_Tech_QA"
TECH2_NAME = "TEST_Tech2_QA"


def login(creds):
    r = requests.post(f"{API}/auth/login", json={"email": creds[0], "password": creds[1]}, timeout=40)
    if r.status_code != 200:
        pytest.fail(f"Login failed for {creds[0]}: {r.status_code} {r.text[:300]}")
    tok = r.json().get("token")
    assert tok, f"No token for {creds[0]}"
    return tok


def client_for(creds):
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json", "Authorization": f"Bearer {login(creds)}"})
    return s


# ---------------- K8s probes ----------------
class TestHealthProbes:
    def test_health_no_auth(self):
        r = requests.get(f"{BASE}/health", timeout=30)
        assert r.status_code == 200, r.text[:200]

    def test_healthz_no_auth(self):
        r = requests.get(f"{BASE}/healthz", timeout=30)
        assert r.status_code == 200, r.text[:200]

    def test_me_requires_auth(self):
        r = requests.get(f"{API}/auth/me", timeout=30)
        assert r.status_code == 401


# ---------------- Auth ----------------
class TestAuthLoginAllRoles:
    @pytest.mark.parametrize("creds,role", [
        (ADMIN, "admin"), (COMM, "commercial"), (TECH1, "technicien"),
        (TECH2, "technicien"), (ACME, "admin"),
    ])
    def test_login_and_me(self, creds, role):
        tok = login(creds)
        r = requests.get(f"{API}/auth/me", headers={"Authorization": f"Bearer {tok}"}, timeout=30)
        assert r.status_code == 200, r.text[:300]
        me = r.json()
        assert me["email"] == creds[0]
        assert me["role"] == role
        assert me.get("company_id")

    def test_login_bad_password(self):
        r = requests.post(f"{API}/auth/login", json={"email": ADMIN[0], "password": "WRONG_pwd_1"}, timeout=30)
        assert r.status_code in (400, 401, 423), r.status_code


class TestLogoutRevocation:
    """Uses the responsable account only (logout bumps token_epoch for that user)."""
    def test_logout_revokes_token(self):
        tok = login(RESP)
        h = {"Authorization": f"Bearer {tok}"}
        assert requests.get(f"{API}/auth/me", headers=h, timeout=30).status_code == 200
        out = requests.post(f"{API}/auth/logout", headers=h, timeout=30)
        assert out.status_code == 200, out.text[:200]
        again = requests.get(f"{API}/auth/me", headers=h, timeout=30)
        assert again.status_code == 401, f"Token still valid after logout: {again.status_code}"
        assert "voqu" in again.text.lower() or "révoqu" in again.text.lower() or "revoqu" in again.text.lower()
        # fresh login still works
        assert requests.get(f"{API}/auth/me", headers={"Authorization": f"Bearer {login(RESP)}"}, timeout=30).status_code == 200


# ---------------- iter28 commercial bonuses ----------------
class TestBonusesIter28:
    @pytest.fixture(scope="class")
    def admin(self):
        return client_for(ADMIN)

    @pytest.fixture(scope="class")
    def comm(self):
        return client_for(COMM)

    @pytest.fixture(scope="class")
    def state(self):
        return {}

    def test_create_bonus_admin(self, admin, state):
        payload = {"name": f"TEST_QA_Prime_{uuid.uuid4().hex[:6]}", "ca_threshold": 25000,
                   "amount": 500, "period": "month", "commerciaux": ["*"], "active": True,
                   "notify_near": True, "near_threshold_pct": 80}
        r = admin.post(f"{API}/bonuses", json=payload, timeout=40)
        assert r.status_code == 200, r.text[:400]
        b = r.json()
        assert "_id" not in b
        assert b["name"] == payload["name"]
        assert b["ca_threshold"] == 25000
        assert b["amount"] == 500
        assert b["active"] is True
        assert b.get("company_id")
        state["bid"] = b["id"]
        state["bname"] = b["name"]

    def test_list_bonuses_contains_created(self, admin, state):
        r = admin.get(f"{API}/bonuses", timeout=40)
        assert r.status_code == 200, r.text[:300]
        rows = r.json()
        assert isinstance(rows, list)
        assert any(x["id"] == state["bid"] for x in rows)
        assert all("_id" not in x for x in rows)

    def test_progress_endpoint(self, admin, state):
        r = admin.get(f"{API}/bonuses/progress", timeout=60)
        assert r.status_code == 200, r.text[:300]
        rows = r.json()
        assert isinstance(rows, list)
        mine = [x for x in rows if x["bonus_id"] == state["bid"]]
        assert mine, "created bonus missing from progress"
        for x in mine:
            for k in ("commercial", "ca_current", "ca_threshold", "amount", "progress_pct", "reached", "near", "remaining"):
                assert k in x, f"missing {k}"
            assert x["ca_threshold"] == 25000
            assert isinstance(x["reached"], bool)

    def test_progress_with_explicit_commerciaux(self, admin, state):
        """Control test: with an explicit commerciaux list the progress computation works.
        Contrast with test_progress_endpoint (commerciaux=['*']) which returns nothing."""
        payload = {"name": f"TEST_QA_PrimeExpl_{uuid.uuid4().hex[:6]}", "ca_threshold": 10000,
                   "amount": 200, "period": "all", "commerciaux": ["Thomas"], "active": True}
        r = admin.post(f"{API}/bonuses", json=payload, timeout=40)
        assert r.status_code == 200, r.text[:300]
        bid = r.json()["id"]
        try:
            prog = admin.get(f"{API}/bonuses/progress", timeout=60)
            assert prog.status_code == 200, prog.text[:300]
            rows = [x for x in prog.json() if x["bonus_id"] == bid]
            assert len(rows) == 1, f"expected 1 row for explicit commercial, got {rows}"
            row = rows[0]
            assert row["commercial"] == "Thomas"
            assert isinstance(row["ca_current"], (int, float))
            assert row["ca_threshold"] == 10000
            assert row["amount"] == 200
            assert row["reached"] == (row["ca_current"] >= 10000)
            assert row["remaining"] == pytest.approx(max(0.0, 10000 - row["ca_current"]), abs=0.02)
        finally:
            admin.delete(f"{API}/bonuses/{bid}", timeout=40)

    def test_awards_endpoint(self, admin):
        r = admin.get(f"{API}/bonuses/awards", timeout=40)
        assert r.status_code == 200, r.text[:300]
        assert isinstance(r.json(), list)

    def test_commercial_cannot_create(self, comm):
        r = comm.post(f"{API}/bonuses", json={"name": "TEST_QA_Forbidden", "ca_threshold": 1, "amount": 1}, timeout=40)
        assert r.status_code == 403, r.status_code

    def test_commercial_can_read_progress(self, comm):
        r = comm.get(f"{API}/bonuses/progress", timeout=60)
        assert r.status_code == 200, r.text[:300]
        rows = r.json()
        me = comm.get(f"{API}/auth/me", timeout=30).json()
        assert all(x["commercial"] == me.get("name") for x in rows), "commercial sees other commerciaux rows"

    def test_update_bonus_active_false(self, admin, state):
        r = admin.put(f"{API}/bonuses/{state['bid']}", json={"active": False}, timeout=40)
        assert r.status_code == 200, r.text[:300]
        assert r.json()["active"] is False
        # persisted
        rows = admin.get(f"{API}/bonuses", timeout=40).json()
        row = next(x for x in rows if x["id"] == state["bid"])
        assert row["active"] is False
        # inactive bonuses excluded from progress
        prog = admin.get(f"{API}/bonuses/progress", timeout=60).json()
        assert not [x for x in prog if x["bonus_id"] == state["bid"]]

    def test_tenant_isolation_bonuses(self, state):
        acme = client_for(ACME)
        rows = acme.get(f"{API}/bonuses", timeout=40).json()
        assert all(x["id"] != state["bid"] for x in rows), "cross-tenant bonus leak"
        r = acme.put(f"{API}/bonuses/{state['bid']}", json={"amount": 1}, timeout=40)
        assert r.status_code == 404, r.status_code

    def test_delete_bonus(self, admin, state):
        r = admin.delete(f"{API}/bonuses/{state['bid']}", timeout=40)
        assert r.status_code == 200, r.text[:300]
        rows = admin.get(f"{API}/bonuses", timeout=40).json()
        assert all(x["id"] != state["bid"] for x in rows)
        assert admin.delete(f"{API}/bonuses/{state['bid']}", timeout=40).status_code == 404


# ---------------- iter29 technician project bonuses ----------------
class TestProjectBonusesIter29:
    @pytest.fixture(scope="class")
    def admin(self):
        return client_for(ADMIN)

    @pytest.fixture(scope="class")
    def state(self):
        return {}

    @pytest.fixture(scope="class", autouse=True)
    def cleanup(self, admin, state):
        yield
        if state.get("sale_id"):
            admin.delete(f"{API}/sales/{state['sale_id']}", timeout=40)

    def test_setup_project_with_two_techs(self, admin, state):
        sale = {
            "client": {"name": f"TEST_QA_Bonus_{uuid.uuid4().hex[:6]}", "phone": "0600000001"},
            "service": "TEST_QA service", "amount": 1000, "sale_date": "2026-07-10",
            "desired_intervention_date": "2026-07-20", "commercial": "TEST_QA_Evo",
            "commission_rate": 0.1, "status": "commercial_cheque",
        }
        r = admin.post(f"{API}/sales", json=sale, timeout=60)
        assert r.status_code == 200, r.text[:400]
        state["sale_id"] = r.json()["id"]
        projects = admin.get(f"{API}/projects", timeout=60).json()
        proj = next((p for p in projects if p.get("sale_id") == state["sale_id"]), None)
        assert proj, "auto project not created for sale"
        state["pid"] = proj["id"]
        up = admin.put(f"{API}/projects/{state['pid']}",
                       json={"assigned_to": [TECH1_NAME, TECH2_NAME], "scheduled_date": "2026-07-20"}, timeout=40)
        assert up.status_code == 200, up.text[:300]
        assert sorted(up.json()["assigned_to"]) == sorted([TECH1_NAME, TECH2_NAME])

    def test_admin_creates_bonus_for_tech1(self, admin, state):
        r = admin.post(f"{API}/projects/{state['pid']}/bonuses",
                       json={"technician_name": TECH1_NAME, "amount": 50, "note": "TEST_QA prime chantier"}, timeout=40)
        assert r.status_code == 200, r.text[:400]
        b = r.json()
        assert "_id" not in b
        assert b["technician_name"] == TECH1_NAME
        assert b["amount"] == 50.0
        assert b["project_id"] == state["pid"]
        assert b["project_date"].startswith("2026-07")
        state["b1"] = b["id"]

    def test_admin_creates_bonus_for_tech2(self, admin, state):
        r = admin.post(f"{API}/projects/{state['pid']}/bonuses",
                       json={"technician_name": TECH2_NAME, "amount": 30}, timeout=40)
        assert r.status_code == 200, r.text[:400]
        state["b2"] = r.json()["id"]

    def test_upsert_is_idempotent(self, admin, state):
        r = admin.post(f"{API}/projects/{state['pid']}/bonuses",
                       json={"technician_name": TECH1_NAME, "amount": 60}, timeout=40)
        assert r.status_code == 200, r.text[:300]
        assert r.json()["id"] == state["b1"], "duplicate row created instead of update"
        assert r.json()["amount"] == 60.0
        # restore
        admin.post(f"{API}/projects/{state['pid']}/bonuses", json={"technician_name": TECH1_NAME, "amount": 50}, timeout=40)

    def test_admin_sees_all_bonuses(self, admin, state):
        r = admin.get(f"{API}/projects/{state['pid']}/bonuses", timeout=40)
        assert r.status_code == 200, r.text[:300]
        rows = r.json()
        names = {x["technician_name"] for x in rows}
        assert {TECH1_NAME, TECH2_NAME} <= names
        assert len(rows) == 2

    def test_tech1_sees_only_own_bonus(self, state):
        t1 = client_for(TECH1)
        r = t1.get(f"{API}/projects/{state['pid']}/bonuses", timeout=40)
        assert r.status_code == 200, r.text[:300]
        rows = r.json()
        assert len(rows) == 1, f"technician sees {len(rows)} bonuses (expected 1)"
        assert rows[0]["technician_name"] == TECH1_NAME
        assert rows[0]["amount"] == 50.0

    def test_tech_cannot_create_bonus(self, state):
        t1 = client_for(TECH1)
        r = t1.post(f"{API}/projects/{state['pid']}/bonuses",
                    json={"technician_name": TECH1_NAME, "amount": 999}, timeout=40)
        assert r.status_code == 403, r.status_code

    def test_bonus_for_unassigned_tech_400(self, admin, state):
        r = admin.post(f"{API}/projects/{state['pid']}/bonuses",
                       json={"technician_name": "TEST_QA_NotAssigned", "amount": 10}, timeout=40)
        assert r.status_code == 400, f"{r.status_code} {r.text[:200]}"

    def test_bonus_unknown_project_404(self, admin):
        r = admin.post(f"{API}/projects/{uuid.uuid4()}/bonuses",
                       json={"technician_name": TECH1_NAME, "amount": 10}, timeout=40)
        assert r.status_code == 404, r.status_code

    def test_bonus_amount_validation(self, admin, state):
        r = admin.post(f"{API}/projects/{state['pid']}/bonuses",
                       json={"technician_name": TECH1_NAME, "amount": -5}, timeout=40)
        assert r.status_code == 422, r.status_code

    def test_monthly_aggregation_admin(self, admin, state):
        r = admin.get(f"{API}/project-bonuses/monthly", params={"month": "2026-07"}, timeout=60)
        assert r.status_code == 200, r.text[:300]
        rows = r.json()
        t1 = next((x for x in rows if x["technician_name"] == TECH1_NAME), None)
        assert t1, f"TECH1 missing from monthly aggregate: {rows}"
        assert t1["month"] == "2026-07"
        assert t1["total_amount"] >= 50.0
        assert any(i["project_id"] == state["pid"] for i in t1["items"])

    def test_monthly_bad_format_400(self, admin):
        r = admin.get(f"{API}/project-bonuses/monthly", params={"month": "2026/07"}, timeout=40)
        assert r.status_code == 400, r.status_code

    def test_monthly_tech_scoped(self, state):
        t2 = client_for(TECH2)
        r = t2.get(f"{API}/project-bonuses/monthly", params={"month": "2026-07"}, timeout=60)
        assert r.status_code == 200, r.text[:300]
        rows = r.json()
        assert all(x["technician_name"].lower() == TECH2_NAME.lower() for x in rows), rows

    def test_tenant_isolation_project_bonuses(self, state):
        acme = client_for(ACME)
        r = acme.get(f"{API}/projects/{state['pid']}/bonuses", timeout=40)
        assert r.status_code == 404, f"cross-tenant project visible: {r.status_code}"
        m = acme.get(f"{API}/project-bonuses/monthly", params={"month": "2026-07"}, timeout=60)
        assert m.status_code == 200
        assert all(x["technician_name"] not in (TECH1_NAME, TECH2_NAME) for x in m.json()), "cross-tenant bonus leak"
        upd = acme.put(f"{API}/project-bonuses/{state['b1']}", json={"amount": 1}, timeout=40)
        assert upd.status_code == 404
        dele = acme.delete(f"{API}/project-bonuses/{state['b1']}", timeout=40)
        assert dele.status_code == 404

    def test_update_and_delete_project_bonus(self, admin, state):
        r = admin.put(f"{API}/project-bonuses/{state['b2']}", json={"amount": 75, "note": "TEST_QA upd"}, timeout=40)
        assert r.status_code == 200, r.text[:300]
        assert r.json()["amount"] == 75.0
        assert r.json()["note"] == "TEST_QA upd"
        rows = admin.get(f"{API}/projects/{state['pid']}/bonuses", timeout=40).json()
        assert next(x for x in rows if x["id"] == state["b2"])["amount"] == 75.0
        for bid in (state["b1"], state["b2"]):
            d = admin.delete(f"{API}/project-bonuses/{bid}", timeout=40)
            assert d.status_code == 200, d.text[:200]
        assert admin.get(f"{API}/projects/{state['pid']}/bonuses", timeout=40).json() == []


# ---------------- iter23 project notes ----------------
class TestProjectNotesIter23:
    @pytest.fixture(scope="class")
    def admin(self):
        return client_for(ADMIN)

    @pytest.fixture(scope="class")
    def state(self):
        return {}

    @pytest.fixture(scope="class", autouse=True)
    def setup(self, admin, state):
        sale = {
            "client": {"name": f"TEST_QA_Notes_{uuid.uuid4().hex[:6]}", "phone": "0600000002"},
            "service": "TEST_QA notes", "amount": 500, "sale_date": "2026-07-11",
            "desired_intervention_date": "2026-07-21", "commercial": "TEST_QA_Evo",
            "commission_rate": 0.1, "status": "commercial_cheque",
        }
        r = admin.post(f"{API}/sales", json=sale, timeout=60)
        assert r.status_code == 200, r.text[:400]
        state["sale_id"] = r.json()["id"]
        proj = next(p for p in admin.get(f"{API}/projects", timeout=60).json() if p.get("sale_id") == state["sale_id"])
        state["pid"] = proj["id"]
        admin.put(f"{API}/projects/{state['pid']}", json={"assigned_to": [TECH1_NAME, TECH2_NAME]}, timeout=40)
        yield
        admin.delete(f"{API}/sales/{state['sale_id']}", timeout=40)

    def test_tech_writes_own_note(self, state):
        t1 = client_for(TECH1)
        r = t1.put(f"{API}/projects/{state['pid']}/notes/{TECH1_NAME}", json={"note": "TEST_QA note tech1"}, timeout=40)
        assert r.status_code == 200, r.text[:300]
        assert r.json()["note"] == "TEST_QA note tech1"
        assert "_id" not in r.json()

    def test_admin_writes_note_for_tech2(self, admin, state):
        r = admin.put(f"{API}/projects/{state['pid']}/notes/{TECH2_NAME}", json={"note": "TEST_QA note tech2"}, timeout=40)
        assert r.status_code == 200, r.text[:300]

    def test_tech_cross_write_403(self, state):
        t1 = client_for(TECH1)
        r = t1.put(f"{API}/projects/{state['pid']}/notes/{TECH2_NAME}", json={"note": "hack"}, timeout=40)
        assert r.status_code == 403, r.status_code

    def test_tech_sees_only_own_note(self, state):
        t1 = client_for(TECH1)
        rows = t1.get(f"{API}/projects/{state['pid']}/notes", timeout=40)
        assert rows.status_code == 200, rows.text[:300]
        data = rows.json()
        assert len(data) == 1 and data[0]["technician_name"] == TECH1_NAME, data

    def test_admin_sees_all_notes(self, admin, state):
        data = admin.get(f"{API}/projects/{state['pid']}/notes", timeout=40).json()
        assert {x["technician_name"] for x in data} == {TECH1_NAME, TECH2_NAME}

    def test_tech_delete_note_403(self, state):
        t1 = client_for(TECH1)
        r = t1.delete(f"{API}/projects/{state['pid']}/notes/{TECH1_NAME}", timeout=40)
        assert r.status_code == 403, r.status_code

    def test_admin_delete_note(self, admin, state):
        r = admin.delete(f"{API}/projects/{state['pid']}/notes/{TECH1_NAME}", timeout=40)
        assert r.status_code == 200, r.text[:200]
        data = admin.get(f"{API}/projects/{state['pid']}/notes", timeout=40).json()
        assert all(x["technician_name"] != TECH1_NAME for x in data)


# ---------------- iter25 AI corrections ----------------
class TestAICorrectionsIter25:
    @pytest.fixture(scope="class")
    def admin(self):
        return client_for(ADMIN)

    @pytest.fixture(scope="class")
    def state(self):
        return {}

    def test_admin_can_log_correction(self, admin, state):
        marker = f"TEST_QA_{uuid.uuid4().hex[:6]}"
        r = admin.post(f"{API}/ai/corrections",
                       json={"field": "client_name", "ai_value": "Jhon", "corrected_value": marker,
                             "context": {"src": "qa"}}, timeout=40)
        assert r.status_code == 200, r.text[:300]
        assert r.json().get("ok") is True
        state["marker"] = marker

    def test_list_corrections(self, admin, state):
        r = admin.get(f"{API}/ai/corrections", timeout=40)
        assert r.status_code == 200, r.text[:300]
        rows = r.json()
        assert all("_id" not in x for x in rows)
        row = next((x for x in rows if x.get("corrected_value") == state["marker"]), None)
        assert row, "correction not persisted"
        assert row["field"] == "client_name"
        assert row["ai_value"] == "Jhon"
        state["cid"] = row["id"]

    def test_empty_corrected_value_not_persisted(self, admin):
        before = len(admin.get(f"{API}/ai/corrections", timeout=40).json())
        r = admin.post(f"{API}/ai/corrections", json={"field": "amount", "ai_value": "1", "corrected_value": "  "}, timeout=40)
        assert r.status_code == 200
        after = len(admin.get(f"{API}/ai/corrections", timeout=40).json())
        assert after == before, "blank correction was persisted"

    def test_commercial_forbidden(self):
        comm = client_for(COMM)
        assert comm.post(f"{API}/ai/corrections", json={"field": "x", "corrected_value": "y"}, timeout=40).status_code == 403
        assert comm.get(f"{API}/ai/corrections", timeout=40).status_code == 403

    def test_tenant_isolation(self, state):
        acme = client_for(ACME)
        rows = acme.get(f"{API}/ai/corrections", timeout=40).json()
        assert all(x.get("corrected_value") != state["marker"] for x in rows), "cross-tenant AI correction leak"
        assert acme.delete(f"{API}/ai/corrections/{state['cid']}", timeout=40).status_code == 404

    def test_delete_correction(self, admin, state):
        r = admin.delete(f"{API}/ai/corrections/{state['cid']}", timeout=40)
        assert r.status_code == 200, r.text[:200]
        rows = admin.get(f"{API}/ai/corrections", timeout=40).json()
        assert all(x["id"] != state["cid"] for x in rows)
        assert admin.delete(f"{API}/ai/corrections/{state['cid']}", timeout=40).status_code == 404


# ---------------- iter27 flexible commissions + sales regression ----------------
class TestCommissionsIter27:
    NAME = f"TEST_QA_Evo_{uuid.uuid4().hex[:5]}"

    @pytest.fixture(scope="class")
    def admin(self):
        return client_for(ADMIN)

    @pytest.fixture(scope="class")
    def cfg(self, admin):
        r = admin.get(f"{API}/settings", timeout=40)
        assert r.status_code == 200, r.text[:300]
        s = r.json()
        return {
            "threshold": float(s.get("commission_ca_threshold", 30000) or 30000),
            "before": float(s.get("commission_ca_rate_before", 0.10) or 0.10),
            "after": float(s.get("commission_ca_rate_after", 0.15) or 0.15),
        }

    @pytest.fixture(scope="class")
    def state(self):
        return {"sales": []}

    @pytest.fixture(scope="class", autouse=True)
    def cleanup(self, admin, state):
        yield
        for sid in state["sales"]:
            admin.delete(f"{API}/sales/{sid}", timeout=40)

    def _mk(self, admin, state, amount, ctype, rate=0.0, day="12"):
        payload = {
            "client": {"name": f"TEST_QA_Comm_{uuid.uuid4().hex[:6]}", "phone": "0600000003"},
            "service": "TEST_QA comm", "amount": amount, "sale_date": f"2026-07-{day}",
            "commercial": self.NAME, "commission_rate": rate, "commission_type": ctype,
            "status": "commercial_cheque",
        }
        r = admin.post(f"{API}/sales", json=payload, timeout=60)
        assert r.status_code == 200, r.text[:400]
        sid = r.json()["id"]
        state["sales"].append(sid)
        assert r.json()["commission_type"] == ctype
        return sid

    def _rows(self, admin):
        r = admin.get(f"{API}/commissions", timeout=60)
        assert r.status_code == 200, r.text[:300]
        return [x for x in r.json() if x.get("commercial") == self.NAME]

    def test_evolutive_below_threshold_uses_before_rate(self, admin, state, cfg):
        amt = cfg["threshold"] * 0.5
        sid = self._mk(admin, state, amt, "evolutive_ca")
        row = next(x for x in self._rows(admin) if x["sale_id"] == sid)
        assert row["commission_type"] == "evolutive_ca"
        assert row["commission_rate"] == pytest.approx(cfg["before"]), row
        assert row["commission_amount"] == pytest.approx(round(amt * cfg["before"], 2))

    def test_evolutive_above_threshold_uses_after_rate(self, admin, state, cfg):
        # push cumulative evolutive CA above the threshold
        sid2 = self._mk(admin, state, cfg["threshold"] * 0.8, "evolutive_ca", day="13")
        rows = self._rows(admin)
        evo = [x for x in rows if x["commission_type"] == "evolutive_ca"]
        assert len(evo) >= 2
        for x in evo:
            assert x["commission_rate"] == pytest.approx(cfg["after"]), x
        r2 = next(x for x in rows if x["sale_id"] == sid2)
        assert r2["commission_amount"] == pytest.approx(round(cfg["threshold"] * 0.8 * cfg["after"], 2))

    def test_fixed_stays_at_declared_rate(self, admin, state):
        sid = self._mk(admin, state, 5000, "fixed", rate=0.10, day="14")
        row = next(x for x in self._rows(admin) if x["sale_id"] == sid)
        assert row["commission_type"] == "fixed"
        assert row["commission_rate"] == pytest.approx(0.10), row
        assert row["commission_amount"] == pytest.approx(500.0)

    def test_switch_type_via_put_inline(self, admin, state):
        sid = state["sales"][-1]
        r = admin.put(f"{API}/sales/{sid}", json={"commission_rate": 0.13}, timeout=40)
        assert r.status_code == 200, r.text[:300]
        assert r.json()["commission_rate"] == 0.13
        row = next(x for x in self._rows(admin) if x["sale_id"] == sid)
        assert row["commission_rate"] == pytest.approx(0.13)

    def test_sales_list_regression(self, admin, state):
        r = admin.get(f"{API}/sales", timeout=60)
        assert r.status_code == 200, r.text[:300]
        sales = r.json()
        assert isinstance(sales, list)
        assert all("_id" not in s for s in sales)
        found = [s for s in sales if s["id"] in state["sales"]]
        assert len(found) == len(state["sales"])
        for s in found:
            assert s["client_name"].startswith("TEST_QA_Comm_")
            assert "commission_type" in s

    def test_commissions_tenant_isolation(self):
        acme = client_for(ACME)
        r = acme.get(f"{API}/commissions", timeout=60)
        assert r.status_code == 200, r.text[:300]
        assert all(x.get("commercial") != self.NAME for x in r.json()), "cross-tenant commission leak"
