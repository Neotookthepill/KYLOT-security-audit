"""Iteration 17 — Absences, RAC payment method, editable commission rates (KEYLOT).

Covers:
- /api/absences GET/POST/DELETE + validation + RBAC (technicien 403) + tenant isolation
- /api/settings commission_rates persistence/normalisation
- /api/sales with payment_method='rac' + aggregation endpoints regression
"""
import os
import uuid
from datetime import date, timedelta

import pytest
import requests
from dotenv import dotenv_values

frontend_env = dotenv_values("/app/frontend/.env")
_b = os.environ.get("REACT_APP_BACKEND_URL") or frontend_env.get("REACT_APP_BACKEND_URL")
if not _b:
    raise RuntimeError("REACT_APP_BACKEND_URL missing")
BASE = _b.rstrip("/") + "/api"

SUPER = ("super@keylot.app", "Super@2026")
ADMIN = ("admin@example.invalid", "CHANGE_ME_TEST_PASSWORD")
TECH = ("test-tech@keylot.app", "Tech@2026", "TEST_Tech_QA")
TODAY = date.today().isoformat()
TOMORROW = (date.today() + timedelta(days=2)).isoformat()


def _login(email, password):
    return requests.post(f"{BASE}/auth/login", json={"email": email, "password": password}, timeout=30)


def _client(email, password):
    r = _login(email, password)
    if r.status_code != 200:
        pytest.fail(f"Login failed {email}: {r.status_code} {r.text[:300]}")
    s = requests.Session()
    s.headers.update({"Authorization": f"Bearer {r.json()['token']}", "Content-Type": "application/json"})
    return s


@pytest.fixture(scope="module")
def admin_c():
    return _client(*ADMIN)


@pytest.fixture(scope="module")
def super_c():
    return _client(*SUPER)


@pytest.fixture(scope="module")
def tech_c(admin_c):
    if _login(TECH[0], TECH[1]).status_code != 200:
        r = admin_c.post(f"{BASE}/users", json={"email": TECH[0], "password": TECH[1], "name": TECH[2], "role": "technicien"})
        assert r.status_code in (200, 201, 400), r.text
    return _client(TECH[0], TECH[1])


@pytest.fixture(scope="module")
def other_tenant(super_c):
    """Create a disposable company + admin for isolation checks; delete at teardown."""
    slug = uuid.uuid4().hex[:6]
    payload = {
        "name": f"TEST_ISO_{slug}",
        "admin_email": f"iso-{slug}@keylot.example.com",
        "admin_password": "Iso@2026!",
        "admin_name": "TEST Iso Admin",
    }
    r = super_c.post(f"{BASE}/superadmin/companies", json=payload)
    if r.status_code not in (200, 201):
        pytest.fail(f"Company creation failed: {r.status_code} {r.text[:400]}")
    cid = r.json().get("id") or r.json().get("company", {}).get("id")
    c = _client(payload["admin_email"], payload["admin_password"])
    yield c
    if cid:
        super_c.delete(f"{BASE}/superadmin/companies/{cid}")


# ---------------- Absences ----------------
class TestAbsences:
    def test_list_absences(self, admin_c):
        r = admin_c.get(f"{BASE}/absences")
        assert r.status_code == 200, r.text
        assert isinstance(r.json(), list)
        for a in r.json():
            assert "_id" not in a

    def test_create_and_persist(self, admin_c):
        payload = {"person_name": "TEST_Abs_Tech", "person_type": "technicien",
                   "date_from": TODAY, "date_to": TOMORROW, "reason": "TEST_Conge"}
        r = admin_c.post(f"{BASE}/absences", json=payload)
        assert r.status_code in (200, 201), r.text
        doc = r.json()
        aid = doc["id"]
        assert doc["person_name"] == payload["person_name"]
        assert doc["person_type"] == "technicien"
        assert doc["date_from"] == TODAY and doc["date_to"] == TOMORROW
        assert doc["reason"] == "TEST_Conge"
        assert "company_id" in doc
        assert "_id" not in doc

        got = admin_c.get(f"{BASE}/absences").json()
        assert any(a["id"] == aid for a in got), "created absence not returned by GET"

        # month filter
        rm = admin_c.get(f"{BASE}/absences", params={"month": TODAY[:7]})
        assert rm.status_code == 200
        assert any(a["id"] == aid for a in rm.json())

        d = admin_c.delete(f"{BASE}/absences/{aid}")
        assert d.status_code == 200, d.text
        assert not any(a["id"] == aid for a in admin_c.get(f"{BASE}/absences").json())

    def test_reject_reversed_dates(self, admin_c):
        r = admin_c.post(f"{BASE}/absences", json={
            "person_name": "TEST_Bad", "person_type": "technicien",
            "date_from": TOMORROW, "date_to": TODAY})
        assert r.status_code == 400, r.text

    def test_reject_invalid_person_type(self, admin_c):
        r = admin_c.post(f"{BASE}/absences", json={
            "person_name": "TEST_Bad", "person_type": "plombier",
            "date_from": TODAY, "date_to": TODAY})
        assert r.status_code == 422, r.text

    def test_reject_bad_date_format(self, admin_c):
        r = admin_c.post(f"{BASE}/absences", json={
            "person_name": "TEST_Bad", "person_type": "commercial",
            "date_from": "01/07/2026", "date_to": "01/07/2026"})
        assert r.status_code == 422, r.text

    def test_reject_empty_name(self, admin_c):
        r = admin_c.post(f"{BASE}/absences", json={
            "person_name": "", "person_type": "commercial",
            "date_from": TODAY, "date_to": TODAY})
        assert r.status_code == 422, r.text

    def test_delete_unknown_404(self, admin_c):
        r = admin_c.delete(f"{BASE}/absences/{uuid.uuid4()}")
        assert r.status_code == 404, r.text

    def test_unauthenticated_401(self):
        assert requests.get(f"{BASE}/absences", timeout=30).status_code in (401, 403)


class TestAbsencesRBAC:
    def test_technicien_cannot_create(self, tech_c):
        r = tech_c.post(f"{BASE}/absences", json={
            "person_name": "TEST_ByTech", "person_type": "technicien",
            "date_from": TODAY, "date_to": TODAY})
        assert r.status_code == 403, f"expected 403, got {r.status_code} {r.text[:200]}"

    def test_technicien_can_get(self, tech_c):
        r = tech_c.get(f"{BASE}/absences")
        assert r.status_code == 200, r.text

    def test_technicien_cannot_delete(self, admin_c, tech_c):
        created = admin_c.post(f"{BASE}/absences", json={
            "person_name": "TEST_Abs_RBAC", "person_type": "technicien",
            "date_from": TODAY, "date_to": TODAY}).json()
        aid = created["id"]
        try:
            r = tech_c.delete(f"{BASE}/absences/{aid}")
            assert r.status_code == 403, f"expected 403, got {r.status_code}"
            assert any(a["id"] == aid for a in admin_c.get(f"{BASE}/absences").json())
        finally:
            admin_c.delete(f"{BASE}/absences/{aid}")


class TestAbsencesIsolation:
    def test_no_cross_tenant_leak(self, admin_c, other_tenant):
        a = admin_c.post(f"{BASE}/absences", json={
            "person_name": "TEST_Abs_TenantA", "person_type": "commercial",
            "date_from": TODAY, "date_to": TODAY}).json()
        aid = a["id"]
        try:
            other = other_tenant.get(f"{BASE}/absences")
            assert other.status_code == 200, other.text
            assert not any(x["id"] == aid for x in other.json()), "cross-tenant absence leak!"

            b = other_tenant.post(f"{BASE}/absences", json={
                "person_name": "TEST_Abs_TenantB", "person_type": "technicien",
                "date_from": TODAY, "date_to": TODAY})
            assert b.status_code in (200, 201), b.text
            bid = b.json()["id"]
            assert not any(x["id"] == bid for x in admin_c.get(f"{BASE}/absences").json())

            # cross-tenant delete must 404
            assert other_tenant.delete(f"{BASE}/absences/{aid}").status_code == 404
            assert admin_c.delete(f"{BASE}/absences/{bid}").status_code == 404
            other_tenant.delete(f"{BASE}/absences/{bid}")
        finally:
            admin_c.delete(f"{BASE}/absences/{aid}")


# ---------------- Settings commission_rates ----------------
class TestCommissionRates:
    @pytest.fixture(scope="class", autouse=True)
    def restore_rates(self, admin_c):
        original = admin_c.get(f"{BASE}/settings").json().get("commission_rates")
        yield
        if original:
            admin_c.put(f"{BASE}/settings", json={"commission_rates": original})

    def test_get_returns_rates(self, admin_c):
        r = admin_c.get(f"{BASE}/settings")
        assert r.status_code == 200, r.text
        rates = r.json().get("commission_rates")
        assert isinstance(rates, list) and len(rates) > 0
        assert all(isinstance(x, (int, float)) and 0 <= x <= 1 for x in rates)

    def test_put_persists_sorted_dedup(self, admin_c):
        r = admin_c.put(f"{BASE}/settings", json={"commission_rates": [0.22, 0.1, 0, 0.15, 0.1]})
        assert r.status_code == 200, r.text
        assert r.json()["commission_rates"] == [0, 0.1, 0.15, 0.22]
        assert admin_c.get(f"{BASE}/settings").json()["commission_rates"] == [0, 0.1, 0.15, 0.22]

    def test_out_of_range_filtered(self, admin_c):
        r = admin_c.put(f"{BASE}/settings", json={"commission_rates": [-0.5, 0.18, 1.5, 0.3]})
        assert r.status_code == 200, r.text
        assert r.json()["commission_rates"] == [0.18, 0.3]

    def test_non_admin_cannot_modify(self, tech_c):
        r = tech_c.put(f"{BASE}/settings", json={"commission_rates": [0.99]})
        assert r.status_code == 403, f"expected 403, got {r.status_code}"


# ---------------- RAC payment method ----------------
class TestRacSale:
    @pytest.fixture(scope="class")
    def client_id(self, admin_c):
        r = admin_c.post(f"{BASE}/clients", json={
            "name": "TEST_RAC_Client", "phone": "0600000017",
            "address": "1 rue du Test", "postal_code": "75001", "city": "Paris"})
        assert r.status_code in (200, 201), r.text
        cid = r.json()["id"]
        yield cid
        admin_c.delete(f"{BASE}/clients/{cid}")

    def test_create_rac_sale(self, admin_c, client_id):
        payload = {
            "client_id": client_id,
            "bdc": f"TEST-RAC-{uuid.uuid4().hex[:5]}",
            "service": "TEST_Service RAC",
            "amount": 5000,
            "payment_method": "rac",
            "commission_rate": 0.15,
            "sale_date": TODAY,
            "commercial": "QA",
            "status": "commercial_cheque",
        }
        r = admin_c.post(f"{BASE}/sales", json=payload)
        assert r.status_code in (200, 201), r.text
        sale = r.json()
        sid = sale["id"]
        assert sale["payment_method"] == "rac"
        assert sale["commission_rate"] == 0.15
        try:
            listing = admin_c.get(f"{BASE}/sales").json()
            rows = listing if isinstance(listing, list) else listing.get("items", [])
            persisted = [s for s in rows if s["id"] == sid]
            assert persisted, "RAC sale missing from /sales"
            assert persisted[0]["payment_method"] == "rac"
            assert persisted[0]["amount"] == 5000

            dash = admin_c.get(f"{BASE}/dashboard/stats")
            assert dash.status_code == 200, dash.text
            dexec = admin_c.get(f"{BASE}/dashboard/executive")
            assert dexec.status_code == 200, dexec.text
            comm = admin_c.get(f"{BASE}/commissions")
            assert comm.status_code == 200, comm.text
            crows = comm.json() if isinstance(comm.json(), list) else comm.json().get("items", [])
            match = [c for c in crows if c.get("sale_id") == sid or c.get("id") == sid]
            if match:
                assert abs(match[0]["commission_amount"] - 750.0) < 0.01
        finally:
            admin_c.delete(f"{BASE}/sales/{sid}")
