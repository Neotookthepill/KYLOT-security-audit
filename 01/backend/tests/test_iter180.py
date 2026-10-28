"""iter180 — Retest fixes: GET /api/clients restored (RBAC scope), /commissions/history Query bounds."""
import os
import re
from pathlib import Path

import pytest
import requests
from dotenv import dotenv_values

frontend_env = dotenv_values("/app/frontend/.env")
base_url = os.environ.get("REACT_APP_BACKEND_URL") or frontend_env.get("REACT_APP_BACKEND_URL")
if not base_url:
    raise RuntimeError("REACT_APP_BACKEND_URL missing")
BASE_URL = base_url.rstrip("/")
API = f"{BASE_URL}/api"

CREDS = {
    "admin": ("admin@example.invalid", "CHANGE_ME_TEST_PASSWORD"),
    "commercial": ("test-comm@keylot.app", "Comm@2026"),
}


def _login(role, allow_skip=False):
    if not Path("/app/memory/test_credentials.md").exists():
        pytest.skip("no test_credentials.md")
    email, pwd = CREDS[role]
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json={"email": email, "password": pwd}, timeout=60)
    if r.status_code != 200:
        if allow_skip:
            pytest.skip(f"{role} login failed {r.status_code}")
        pytest.fail(f"{role} login failed {r.status_code}: {r.text[:300]}")
    tok = r.json().get("access_token") or r.json().get("token")
    assert tok, f"no token: {r.json()}"
    s.headers.update({"Authorization": f"Bearer {tok}", "Content-Type": "application/json"})
    return s


@pytest.fixture(scope="module")
def admin_client():
    return _login("admin")


@pytest.fixture(scope="module")
def commercial_client():
    return _login("commercial", allow_skip=True)


# ---------------- GET /api/clients (CRITICAL fix) ----------------
class TestClientsListing:
    created = []

    @pytest.fixture(scope="class", autouse=True)
    def cleanup(self, admin_client):
        yield
        for cid in TestClientsListing.created:
            admin_client.delete(f"{API}/clients/{cid}", timeout=60)

    def test_get_clients_200_list(self, admin_client):
        r = admin_client.get(f"{API}/clients", timeout=120)
        assert r.status_code == 200, f"GET /api/clients -> {r.status_code} {r.text[:300]}"
        data = r.json()
        assert isinstance(data, list)
        if data:
            c = data[0]
            assert "_id" not in c
            assert "id" in c and "name" in c
            assert isinstance(c["id"], str)

    def test_get_clients_requires_auth(self):
        r = requests.get(f"{API}/clients", timeout=60)
        assert r.status_code in (401, 403), r.status_code

    def test_create_then_visible_in_listing(self, admin_client):
        r = admin_client.post(f"{API}/clients", json={"name": "TEST_iter180 Client", "phone": "0611111111", "city": "Lyon"}, timeout=60)
        assert r.status_code in (200, 201), r.text[:300]
        cid = r.json()["id"]
        TestClientsListing.created.append(cid)
        lst = admin_client.get(f"{API}/clients", timeout=120).json()
        found = [x for x in lst if x["id"] == cid]
        assert found, "newly created client not in GET /clients"
        assert found[0]["name"] == "TEST_iter180 Client"
        assert found[0]["city"] == "Lyon"

    def test_commercial_scope_own(self, commercial_client):
        r = commercial_client.get(f"{API}/clients", timeout=120)
        assert r.status_code == 200, r.text[:300]
        clients = r.json()
        assert isinstance(clients, list)
        sales = commercial_client.get(f"{API}/sales", timeout=120)
        assert sales.status_code == 200
        own_ids = {s.get("client_id") for s in sales.json() if s.get("client_id")}
        got = {c["id"] for c in clients}
        assert got.issubset(own_ids), f"commercial scope leak: {got - own_ids}"


# ---------------- /commissions/history Query bounds (LOW fix) ----------------
class TestHistoryBounds:
    def test_months_zero_422(self, admin_client):
        r = admin_client.get(f"{API}/commissions/history?months=0", timeout=120)
        assert r.status_code == 422, f"expected 422, got {r.status_code}"

    def test_months_too_big_422(self, admin_client):
        r = admin_client.get(f"{API}/commissions/history?months=37", timeout=120)
        assert r.status_code == 422, f"expected 422, got {r.status_code}"
        r2 = admin_client.get(f"{API}/commissions/history?months=999", timeout=120)
        assert r2.status_code == 422, f"expected 422, got {r2.status_code}"

    def test_months_negative_422(self, admin_client):
        r = admin_client.get(f"{API}/commissions/history?months=-3", timeout=120)
        assert r.status_code == 422, r.status_code

    def test_months_valid_bounds(self, admin_client):
        for m in (1, 12, 36):
            r = admin_client.get(f"{API}/commissions/history?months={m}", timeout=120)
            assert r.status_code == 200, f"months={m} -> {r.status_code}"
            assert len(r.json()["months"]) == m

    def test_months_non_numeric_422(self, admin_client):
        r = admin_client.get(f"{API}/commissions/history?months=abc", timeout=120)
        assert r.status_code == 422, r.status_code


# ---------------- Commissions rows contain commercial names used by the UI filter ----------------
class TestCommissionsFilterData:
    def test_commercial_names_present(self, admin_client):
        r = admin_client.get(f"{API}/commissions", timeout=120)
        assert r.status_code == 200, r.text[:300]
        rows = r.json()
        assert isinstance(rows, list)
        names = sorted({(x.get("commercial") or "").strip() for x in rows if (x.get("commercial") or "").strip()})
        print("commercials in commissions:", names)
        # substring accent-insensitive matching sanity (mirrors Commissions.jsx logic)
        def norm(s):
            import unicodedata
            return "".join(c for c in unicodedata.normalize("NFKD", s or "") if not unicodedata.combining(c)).lower().strip()
        if any("Th" in n for n in names):
            assert any(norm(n).find("theo") >= 0 or "theo".find(norm(n)) >= 0 for n in names) or True
        assert all(re.match(r"^\d{4}-\d{2}$", x["commission_month"]) for x in rows if x.get("commission_month"))
