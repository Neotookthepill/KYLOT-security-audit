"""Iteration 14 — Multi-tenant isolation + RBAC permission enforcement tests (KEYLOT).

Covers:
- auth/me returns company_id + permissions
- super-admin company CRUD + cascade delete
- cross-company data isolation (new company admin sees nothing from 'default')
- default admin regression on every existing endpoint
- permissions endpoints + roles/defaults
- commercial 'own' scope + 403 enforcement
- technicien overtime self-only + admin validation
"""
import os
import uuid

import pytest
import requests
from dotenv import dotenv_values

frontend_env = dotenv_values("/app/frontend/.env")
base_url = os.environ.get("REACT_APP_BACKEND_URL") or frontend_env.get("REACT_APP_BACKEND_URL")
if not base_url:
    raise RuntimeError("REACT_APP_BACKEND_URL missing")
BASE = base_url.rstrip("/") + "/api"

SUPER = ("super@keylot.app", "Super@2026")
ADMIN = ("admin@example.invalid", "CHANGE_ME_TEST_PASSWORD")
COMM = ("test-comm@keylot.app", "Comm@2026")
COMM_NAME = "Thomas"
TECH_EMAIL = "test-tech@keylot.app"
TECH_PASS = "Tech@2026"
TECH_NAME = "TEST_Tech_QA"


def _login(email, password):
    r = requests.post(f"{BASE}/auth/login", json={"email": email, "password": password}, timeout=30)
    return r


def _client(email, password):
    r = _login(email, password)
    if r.status_code != 200:
        pytest.fail(f"Login failed for {email}: {r.status_code} {r.text[:300]}")
    s = requests.Session()
    s.headers.update({"Authorization": f"Bearer {r.json()['token']}", "Content-Type": "application/json"})
    return s


@pytest.fixture(scope="session")
def super_c():
    return _client(*SUPER)


@pytest.fixture(scope="session")
def admin_c():
    return _client(*ADMIN)


@pytest.fixture(scope="session")
def comm_c(admin_c):
    """Ensure the commercial test user exists (name Thomas) then login."""
    if _login(*COMM).status_code != 200:
        r = admin_c.post(f"{BASE}/users", json={
            "email": COMM[0], "password": COMM[1], "name": COMM_NAME, "role": "commercial"})
        assert r.status_code in (200, 201, 400), r.text
    # Reset permissions to role defaults (previous iterations left a partial/escalated map)
    users = admin_c.get(f"{BASE}/users").json()
    uid = next(u["id"] for u in users if u["email"] == COMM[0])
    defaults = admin_c.get(f"{BASE}/roles/defaults").json()["commercial"]
    admin_c.put(f"{BASE}/users/{uid}/permissions", json={"permissions": defaults})
    return _client(*COMM)


@pytest.fixture(scope="session")
def tech_c(admin_c):
    if _login(TECH_EMAIL, TECH_PASS).status_code != 200:
        r = admin_c.post(f"{BASE}/users", json={
            "email": TECH_EMAIL, "password": TECH_PASS, "name": TECH_NAME, "role": "technicien"})
        assert r.status_code in (200, 201, 400), r.text
    return _client(TECH_EMAIL, TECH_PASS)


# ---------------- AUTH ----------------
class TestAuth:
    def test_login_bad_password(self):
        r = _login(ADMIN[0], "wrong-pass")
        assert r.status_code == 401

    def test_me_has_company_and_permissions(self, admin_c):
        r = admin_c.get(f"{BASE}/auth/me")
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["company_id"] == "default"
        assert d["role"] == "admin"
        perms = d["permissions"]
        for res in ("sales", "clients", "projects", "planning", "commissions", "overtime",
                    "reports", "users", "settings", "financial"):
            assert res in perms, f"missing {res} in permissions"
        assert perms["sales"]["view"] == "all"

    def test_super_admin_me(self, super_c):
        d = super_c.get(f"{BASE}/auth/me").json()
        assert d["role"] == "super_admin"

    def test_password_hash_is_bcrypt_2b(self):
        import subprocess
        out = subprocess.run(
            ["python", "-c",
             "import os,asyncio;from motor.motor_asyncio import AsyncIOMotorClient;"
             "from dotenv import dotenv_values;e=dotenv_values('/app/backend/.env');"
             "c=AsyncIOMotorClient(e['MONGO_URL']);"
             "print(asyncio.get_event_loop().run_until_complete("
             "c[e['DB_NAME']].users.find_one({'email':'admin@example.invalid'}))['password_hash'][:4])"],
            capture_output=True, text=True, timeout=60)
        assert "$2b$" in out.stdout, f"bcrypt prefix not found: {out.stdout} {out.stderr[-300:]}"

    def test_unauthenticated_is_401(self):
        for ep in ("/sales", "/clients", "/users", "/superadmin/companies", "/auth/me"):
            r = requests.get(f"{BASE}{ep}", timeout=30)
            assert r.status_code == 401, f"{ep} -> {r.status_code}"


# ---------------- SUPER ADMIN + ISOLATION ----------------
class TestSuperAdminIsolation:
    created = {}

    def test_list_companies(self, super_c):
        r = super_c.get(f"{BASE}/superadmin/companies")
        assert r.status_code == 200, r.text
        data = r.json()
        assert isinstance(data, list) and len(data) >= 1
        ids = [c["id"] for c in data]
        assert "default" in ids
        for c in data:
            assert "user_count" in c and "sales_count" in c

    def test_admin_cannot_list_companies(self, admin_c):
        assert admin_c.get(f"{BASE}/superadmin/companies").status_code == 403

    def test_create_company_with_admin_and_isolation(self, super_c, admin_c):
        suffix = uuid.uuid4().hex[:6]
        email = f"boss-{suffix}@acme.example.com"
        payload = {"name": f"TEST_Acme_{suffix}", "admin_email": email,
                   "admin_password": "Acme@2026", "admin_name": "TEST_Acme Boss"}
        r = super_c.post(f"{BASE}/superadmin/companies", json=payload)
        assert r.status_code == 200, r.text
        body = r.json()
        cid = body["company"]["id"]
        assert body["admin"]["email"] == email
        assert body["admin"]["company_id"] == cid
        TestSuperAdminIsolation.created = {"cid": cid, "email": email}

        # verify it now appears in list
        listed = [c["id"] for c in super_c.get(f"{BASE}/superadmin/companies").json()]
        assert cid in listed

        # ISOLATION: new admin sees nothing from default company
        acme = _client(email, "Acme@2026")
        assert acme.get(f"{BASE}/auth/me").json()["company_id"] == cid
        assert acme.get(f"{BASE}/sales").json() == []
        assert acme.get(f"{BASE}/clients").json() == []
        assert acme.get(f"{BASE}/projects").json() == []
        users = acme.get(f"{BASE}/users").json()
        assert len(users) == 1 and users[0]["email"] == email
        assert acme.get(f"{BASE}/team").json() == []
        ot = acme.get(f"{BASE}/overtime", params={"month": "2026-07"}).json()
        assert ot["entries"] == []
        stats = acme.get(f"{BASE}/dashboard/stats")
        assert stats.status_code == 200, stats.text
        assert float(stats.json().get("total_revenue", 0) or 0) == 0

        # ISOLATION write-side: acme creates a client, default admin must not see it
        cr = acme.post(f"{BASE}/clients", json={"name": f"TEST_AcmeClient_{suffix}", "phone": "0102030405"})
        assert cr.status_code in (200, 201), cr.text
        acme_client_id = cr.json()["id"]
        default_clients = admin_c.get(f"{BASE}/clients").json()
        assert acme_client_id not in [c["id"] for c in default_clients]
        # default admin cannot read/modify acme's client
        assert admin_c.put(f"{BASE}/clients/{acme_client_id}", json={"name": "hack"}).status_code == 404
        # NOTE: DELETE returns 200 {"ok": true} even when nothing matched (misleading status),
        # but the row must NOT be deleted cross-tenant.
        admin_c.delete(f"{BASE}/clients/{acme_client_id}")
        remaining = acme.get(f"{BASE}/clients").json()
        assert len(remaining) == 1 and remaining[0]["id"] == acme_client_id, \
            "CROSS-TENANT DELETE LEAK: default admin deleted another company's client"

    def test_delete_default_company_forbidden(self, super_c):
        r = super_c.delete(f"{BASE}/superadmin/companies/default")
        assert r.status_code == 400

    def test_delete_company_cascades(self, super_c):
        info = TestSuperAdminIsolation.created
        assert info, "company creation test must run first"
        r = super_c.delete(f"{BASE}/superadmin/companies/{info['cid']}")
        assert r.status_code == 200, r.text
        # company gone
        assert info["cid"] not in [c["id"] for c in super_c.get(f"{BASE}/superadmin/companies").json()]
        # admin user gone -> login fails
        assert _login(info["email"], "Acme@2026").status_code == 401


# ---------------- DEFAULT ADMIN REGRESSION ----------------
class TestDefaultAdminRegression:
    def test_sales_list(self, admin_c):
        r = admin_c.get(f"{BASE}/sales")
        assert r.status_code == 200, r.text
        sales = r.json()
        assert len(sales) >= 6, f"expected >=6 default sales, got {len(sales)}"
        for s in sales:
            assert "_id" not in s
            assert s.get("company_id", "default") == "default"

    def test_clients_list(self, admin_c):
        clients = admin_c.get(f"{BASE}/clients").json()
        assert len(clients) >= 10, len(clients)
        assert all("_id" not in c for c in clients)

    def test_projects_list(self, admin_c):
        projects = admin_c.get(f"{BASE}/projects").json()
        assert len(projects) >= 6, len(projects)

    def test_users_list(self, admin_c):
        users = admin_c.get(f"{BASE}/users").json()
        assert len(users) >= 2
        assert all(u.get("company_id", "default") == "default" for u in users)
        assert all("password_hash" not in u for u in users)

    def test_dashboards_reports(self, admin_c):
        for ep, params in (("/dashboard/executive", {"month": "2026-07"}),
                           ("/dashboard/stats", None),
                           ("/commissions", None),
                           ("/reports/monthly", {"month": "2026-07"}),
                           ("/overtime", {"month": "2026-07"}),
                           ("/team", None),
                           ("/settings", None),
                           ("/company/me", None),
                           ("/subscription/me", None)):
            r = admin_c.get(f"{BASE}{ep}", params=params)
            assert r.status_code == 200, f"{ep} -> {r.status_code} {r.text[:200]}"

    def test_sale_crud_cycle(self, admin_c):
        payload = {
            "client": {"name": "TEST_QA_Client14", "phone": "0600000014", "city": "Lyon"},
            "service": "TEST Isolation", "amount": 1234.0, "commercial": COMM_NAME,
            "sale_date": "2026-07-05", "commission_rate": 0.1, "status": "commercial_cheque",
        }
        r = admin_c.post(f"{BASE}/sales", json=payload)
        assert r.status_code in (200, 201), r.text
        sale = r.json()
        sid = sale["id"]
        assert sale["company_id"] == "default"
        assert sale["commercial"] == COMM_NAME
        # GET verify persistence
        got = [s for s in admin_c.get(f"{BASE}/sales").json() if s["id"] == sid]
        assert got and got[0]["amount"] == 1234.0
        # UPDATE
        up = admin_c.put(f"{BASE}/sales/{sid}", json={"amount": 4321.0})
        assert up.status_code == 200, up.text
        got = [s for s in admin_c.get(f"{BASE}/sales").json() if s["id"] == sid]
        assert got[0]["amount"] == 4321.0
        # DELETE
        assert admin_c.delete(f"{BASE}/sales/{sid}").status_code in (200, 204)
        assert sid not in [s["id"] for s in admin_c.get(f"{BASE}/sales").json()]


# ---------------- PERMISSIONS ENDPOINTS ----------------
class TestPermissionsEndpoints:
    def test_roles_defaults(self, admin_c):
        r = admin_c.get(f"{BASE}/roles/defaults")
        assert r.status_code == 200, r.text
        d = r.json()
        assert set(d.keys()) == {"admin", "responsable", "commercial", "technicien", "comptable"}
        assert d["responsable"]["financial"]["view"] is False
        assert d["responsable"]["overtime"]["validate"] is True

    def test_get_and_put_user_permissions(self, admin_c, comm_c):
        me = comm_c.get(f"{BASE}/auth/me").json()
        uid = me["id"]
        r = admin_c.get(f"{BASE}/users/{uid}/permissions")
        assert r.status_code == 200, r.text
        original = r.json()["permissions"]
        assert original["sales"]["view"] == "own"
        # grant reports view
        newp = {**original, "reports": {"view": True}}
        pr = admin_c.put(f"{BASE}/users/{uid}/permissions", json={"permissions": newp})
        assert pr.status_code == 200, pr.text
        assert pr.json()["permissions"]["reports"]["view"] is True
        # persisted
        assert admin_c.get(f"{BASE}/users/{uid}/permissions").json()["permissions"]["reports"]["view"] is True
        # restore
        assert admin_c.put(f"{BASE}/users/{uid}/permissions",
                           json={"permissions": original}).status_code == 200

    def test_permissions_unknown_user_404(self, admin_c):
        assert admin_c.get(f"{BASE}/users/{uuid.uuid4()}/permissions").status_code == 404

    def test_commercial_cannot_read_permissions(self, comm_c):
        me = comm_c.get(f"{BASE}/auth/me").json()
        assert comm_c.get(f"{BASE}/users/{me['id']}/permissions").status_code == 403
        assert comm_c.get(f"{BASE}/roles/defaults").status_code == 403


# ---------------- COMMERCIAL SCOPE ----------------
class TestCommercialScope:
    sid = None
    client_id = None

    def test_setup_own_sale(self, admin_c):
        r = admin_c.post(f"{BASE}/sales", json={
            "client": {"name": "TEST_ThomasClient", "phone": "0611111111"},
            "service": "TEST Thomas sale", "amount": 2000.0, "commercial": COMM_NAME,
            "sale_date": "2026-07-06", "status": "commercial_cheque"})
        assert r.status_code in (200, 201), r.text
        TestCommercialScope.sid = r.json()["id"]
        TestCommercialScope.client_id = r.json()["client_id"]

    def test_commercial_sees_only_own_sales(self, comm_c):
        sales = comm_c.get(f"{BASE}/sales").json()
        assert TestCommercialScope.sid in [s["id"] for s in sales]
        assert all(s.get("commercial") == COMM_NAME for s in sales), \
            f"leak: {[s.get('commercial') for s in sales]}"

    def test_commercial_sees_only_own_clients(self, comm_c):
        clients = comm_c.get(f"{BASE}/clients").json()
        ids = [c["id"] for c in clients]
        assert TestCommercialScope.client_id in ids
        # all clients returned must be linked to one of Thomas's sales
        own_client_ids = {s["client_id"] for s in comm_c.get(f"{BASE}/sales").json()}
        assert set(ids) <= own_client_ids, f"leak: {set(ids) - own_client_ids}"

    def test_commercial_forbidden_endpoints(self, comm_c):
        assert comm_c.get(f"{BASE}/users").status_code == 403
        assert comm_c.get(f"{BASE}/superadmin/companies").status_code == 403
        assert comm_c.put(f"{BASE}/settings", json={"commission_default": 0.5}).status_code == 403
        assert comm_c.post(f"{BASE}/users", json={
            "email": "x@x.com", "password": "aaaaaa", "name": "x", "role": "admin"}).status_code == 403
        assert comm_c.delete(f"{BASE}/sales/{TestCommercialScope.sid}").status_code == 403
        assert comm_c.get(f"{BASE}/reports/monthly", params={"month": "2026-07"}).status_code == 403
        assert comm_c.post(f"{BASE}/overtime", json={
            "technician_name": COMM_NAME, "date": "2026-07-06", "hours": 3}).status_code == 403

    def test_commercial_cannot_touch_foreign_sale(self, admin_c, comm_c):
        r = admin_c.post(f"{BASE}/sales", json={
            "client": {"name": "TEST_OtherClient", "phone": "0622222222"},
            "service": "TEST other", "amount": 500.0, "commercial": "TEST_OtherCommercial",
            "sale_date": "2026-07-07", "status": "commercial_cheque"})
        assert r.status_code in (200, 201), r.text
        other_sid = r.json()["id"]
        other_cid = r.json()["client_id"]
        assert other_sid not in [s["id"] for s in comm_c.get(f"{BASE}/sales").json()]
        assert other_cid not in [c["id"] for c in comm_c.get(f"{BASE}/clients").json()]
        upd = comm_c.put(f"{BASE}/sales/{other_sid}", json={"amount": 1.0})
        assert upd.status_code in (403, 404), f"commercial edited a foreign sale: {upd.status_code}"
        admin_c.delete(f"{BASE}/sales/{other_sid}")
        admin_c.delete(f"{BASE}/clients/{other_cid}")

    def test_commissions_scoped_for_commercial(self, comm_c):
        r = comm_c.get(f"{BASE}/commissions")
        assert r.status_code == 200, r.text

    def test_cleanup_own_sale(self, admin_c):
        if TestCommercialScope.sid:
            admin_c.delete(f"{BASE}/sales/{TestCommercialScope.sid}")
        if TestCommercialScope.client_id:
            admin_c.delete(f"{BASE}/clients/{TestCommercialScope.client_id}")


# ---------------- RESPONSABLE ROLE ----------------
class TestResponsableRole:
    email = "test-resp@keylot.app"
    password = "Resp@2026"

    @pytest.fixture(scope="class")
    def resp_c(self, admin_c):
        if _login(self.email, self.password).status_code != 200:
            r = admin_c.post(f"{BASE}/users", json={
                "email": self.email, "password": self.password,
                "name": "TEST_Resp_QA", "role": "responsable"})
            assert r.status_code in (200, 201, 400), r.text
        return _client(self.email, self.password)

    def test_no_financial_no_sales(self, resp_c):
        assert resp_c.get(f"{BASE}/sales").status_code == 403
        assert resp_c.get(f"{BASE}/commissions").status_code == 403
        assert resp_c.get(f"{BASE}/reports/monthly", params={"month": "2026-07"}).status_code == 403
        assert resp_c.get(f"{BASE}/users").status_code == 403

    def test_can_view_projects_clients_overtime(self, resp_c):
        assert resp_c.get(f"{BASE}/clients").status_code == 200
        assert resp_c.get(f"{BASE}/projects").status_code == 200
        assert resp_c.get(f"{BASE}/overtime", params={"month": "2026-07"}).status_code == 200

    def test_can_validate_overtime(self, resp_c, admin_c):
        r = admin_c.post(f"{BASE}/overtime", json={
            "technician_name": "TEST_ValidateTarget", "date": "2026-07-09", "hours": 2})
        assert r.status_code == 200, r.text
        oid = r.json()["id"]
        v = resp_c.put(f"{BASE}/overtime/{oid}/validate")
        assert v.status_code == 200, v.text
        assert v.json()["status"] == "approved"
        admin_c.post(f"{BASE}/overtime", json={
            "technician_name": "TEST_ValidateTarget", "date": "2026-07-09", "hours": 0})


# ---------------- TECHNICIEN OVERTIME ----------------
class TestTechnicienOvertime:
    oid = None

    def test_declare_own_overtime(self, tech_c):
        r = tech_c.post(f"{BASE}/overtime", json={
            "technician_name": TECH_NAME, "date": "2026-07-08", "hours": 4})
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["status"] == "pending" and d["hours"] == 4
        TestTechnicienOvertime.oid = d["id"]

    def test_cannot_declare_for_other(self, tech_c):
        r = tech_c.post(f"{BASE}/overtime", json={
            "technician_name": "Someone Else", "date": "2026-07-08", "hours": 4})
        assert r.status_code == 403, r.status_code

    def test_tech_sees_only_own_entries(self, tech_c):
        d = tech_c.get(f"{BASE}/overtime", params={"month": "2026-07"}).json()
        assert all(e["technician_name"] == TECH_NAME for e in d["entries"]), d["entries"]

    def test_tech_cannot_validate(self, tech_c):
        assert tech_c.put(f"{BASE}/overtime/{TestTechnicienOvertime.oid}/validate").status_code == 403

    def test_tech_forbidden_business_endpoints(self, tech_c):
        assert tech_c.get(f"{BASE}/sales").status_code == 403
        assert tech_c.get(f"{BASE}/clients").status_code == 403
        assert tech_c.get(f"{BASE}/users").status_code == 403
        assert tech_c.get(f"{BASE}/commissions").status_code == 403

    def test_admin_validates(self, admin_c):
        r = admin_c.put(f"{BASE}/overtime/{TestTechnicienOvertime.oid}/validate")
        assert r.status_code == 200, r.text
        assert r.json()["status"] == "approved"
        entries = admin_c.get(f"{BASE}/overtime", params={"month": "2026-07"}).json()["entries"]
        mine = [e for e in entries if e["id"] == TestTechnicienOvertime.oid]
        assert mine and mine[0]["status"] == "approved"

    def test_cleanup_overtime(self, tech_c):
        r = tech_c.post(f"{BASE}/overtime", json={
            "technician_name": TECH_NAME, "date": "2026-07-08", "hours": 0})
        assert r.status_code == 200
