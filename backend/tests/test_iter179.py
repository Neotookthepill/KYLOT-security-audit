"""iter179 — Tests: GET /api/commissions/history (matrice primes) + photos sur réinterventions."""
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

# 1x1 transparent PNG data URI
PNG = ("data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42m"
       "P8z8DwHwAFAAH/q842iQAAAABJRU5ErkJggg==")


def _creds(role):
    content = Path("/app/memory/test_credentials.md").read_text(encoding="utf-8")
    blocks = {
        "admin": (r"kilianblanc0202@gmail\.com", "CHANGE_ME_TEST_PASSWORD"),
        "commercial": (r"test-comm@keylot\.app", "Comm@2026"),
    }
    pat, pwd = blocks[role]
    m = re.search(pat, content)
    if not m:
        pytest.skip(f"credentials for {role} not found")
    return m.group(0).replace("\\", ""), pwd


@pytest.fixture(scope="module")
def admin_client():
    s = requests.Session()
    email, pwd = _creds("admin")
    r = s.post(f"{API}/auth/login", json={"email": email, "password": pwd}, timeout=60)
    if r.status_code != 200:
        pytest.fail(f"admin login failed {r.status_code}: {r.text[:300]}")
    tok = r.json().get("access_token") or r.json().get("token")
    assert tok, f"no token in login response: {r.json()}"
    s.headers.update({"Authorization": f"Bearer {tok}", "Content-Type": "application/json"})
    return s


@pytest.fixture(scope="module")
def commercial_client():
    s = requests.Session()
    email, pwd = _creds("commercial")
    r = s.post(f"{API}/auth/login", json={"email": email, "password": pwd}, timeout=60)
    if r.status_code != 200:
        pytest.skip(f"commercial login failed {r.status_code}: {r.text[:200]}")
    tok = r.json().get("access_token") or r.json().get("token")
    s.headers.update({"Authorization": f"Bearer {tok}", "Content-Type": "application/json"})
    return s


# ---------------- Commissions history ----------------
class TestCommissionsHistory:
    def test_history_default_structure(self, admin_client):
        r = admin_client.get(f"{API}/commissions/history", timeout=120)
        assert r.status_code == 200, r.text[:400]
        d = r.json()
        for k in ("months", "commercials", "matrix", "totals_by_month", "totals_by_commercial"):
            assert k in d, f"missing key {k}"
        assert isinstance(d["months"], list) and len(d["months"]) == 12
        assert all(re.match(r"^\d{4}-\d{2}$", mk) for mk in d["months"])
        # chronological ascending
        assert d["months"] == sorted(d["months"])
        assert set(d["totals_by_month"].keys()) == set(d["months"])

    @pytest.mark.parametrize("months", [6, 12, 24])
    def test_history_months_param(self, admin_client, months):
        r = admin_client.get(f"{API}/commissions/history?months={months}", timeout=120)
        assert r.status_code == 200, r.text[:300]
        d = r.json()
        assert len(d["months"]) == months
        assert len(d["totals_by_month"]) == months

    def test_history_bounds_rejected(self, admin_client):
        # iter180: Query(ge=1, le=36) -> out-of-range values now rejected with 422
        r = admin_client.get(f"{API}/commissions/history?months=999", timeout=120)
        assert r.status_code == 422, r.status_code
        r0 = admin_client.get(f"{API}/commissions/history?months=0", timeout=120)
        assert r0.status_code == 422, r0.status_code

    def test_history_math_consistency(self, admin_client):
        d = admin_client.get(f"{API}/commissions/history?months=24", timeout=120).json()
        matrix = d["matrix"]
        # commercials list must match matrix keys
        assert set(d["commercials"]) == set(matrix.keys())
        # per-commercial totals == sum of its cells
        for name, cells in matrix.items():
            tot = round(sum(c["total"] for c in cells.values()), 2)
            tc = d["totals_by_commercial"][name]
            assert abs(tc["total"] - tot) < 0.05, f"{name}: {tc['total']} != {tot}"
            assert abs(tc["total"] - (tc["paid"] + tc["to_pay"])) < 0.05
        # per-month totals == sum over commercials
        for mk, tm in d["totals_by_month"].items():
            tot = round(sum((matrix.get(n, {}).get(mk) or {}).get("total", 0) for n in matrix), 2)
            assert abs(tm["total"] - tot) < 0.05, f"{mk}: {tm['total']} != {tot}"
        # grand total == sum of commissions rows in the window (excluding annule/litige)
        rows = admin_client.get(f"{API}/commissions", timeout=120).json()
        mset = set(d["months"])
        expected = round(sum(
            float(r.get("commission_amount") or 0) for r in rows
            if r.get("status") not in ("annule", "litige")
            and (r.get("commission_month") or (r.get("sale_date") or "")[:7]) in mset), 2)
        got = round(sum(t["total"] for t in d["totals_by_month"].values()), 2)
        assert abs(expected - got) < 0.05, f"grand total mismatch: list={expected} history={got}"

    def test_history_requires_auth(self):
        r = requests.get(f"{API}/commissions/history", timeout=60)
        assert r.status_code in (401, 403), r.status_code

    def test_history_scope_commercial(self, commercial_client):
        """RBAC: un commercial ne doit voir que ses propres primes."""
        r = commercial_client.get(f"{API}/commissions/history?months=24", timeout=120)
        assert r.status_code == 200, r.text[:300]
        d = r.json()
        rows = commercial_client.get(f"{API}/commissions", timeout=120).json()
        own_names = {(x.get("commercial") or "").strip() or "—" for x in rows}
        assert set(d["commercials"]).issubset(own_names), (d["commercials"], own_names)
        assert len(d["commercials"]) <= 1, f"commercial scope leaked: {d['commercials']}"


# ---------------- Reinterventions photos ----------------
class TestReinterventionPhotos:
    created = []

    temp_client = []

    @pytest.fixture(scope="class")
    def client_id(self, admin_client):
        # NOTE iter179: GET /api/clients is MISSING (405) — regression. Fallback: derive from /sales,
        # else create a TEST_ client.
        r = admin_client.get(f"{API}/clients", timeout=120)
        if r.status_code == 200 and r.json():
            return r.json()[0]["id"]
        sales = admin_client.get(f"{API}/sales", timeout=120)
        if sales.status_code == 200:
            for s in sales.json():
                if s.get("client_id"):
                    return s["client_id"]
        c = admin_client.post(f"{API}/clients", json={"name": "TEST_iter179 Client", "phone": "0600000000"}, timeout=60)
        assert c.status_code in (200, 201), c.text[:300]
        cid = c.json()["id"]
        TestReinterventionPhotos.temp_client.append(cid)
        return cid

    @pytest.fixture(scope="class", autouse=True)
    def cleanup(self, admin_client):
        yield
        for rid in TestReinterventionPhotos.created:
            admin_client.delete(f"{API}/reinterventions/{rid}", timeout=60)
        for cid in TestReinterventionPhotos.temp_client:
            admin_client.delete(f"{API}/clients/{cid}", timeout=60)

    def test_create_with_photos_and_persist(self, admin_client, client_id):
        payload = {
            "client_id": client_id,
            "technician_name": "",
            "scheduled_date": "2026-07-15",
            "scheduled_time": "09:30",
            "note": "TEST_iter179 photos",
            "photos": [PNG, PNG],
        }
        r = admin_client.post(f"{API}/reinterventions", json=payload, timeout=120)
        assert r.status_code in (200, 201), r.text[:400]
        doc = r.json()
        assert "_id" not in doc
        rid = doc["id"]
        TestReinterventionPhotos.created.append(rid)
        assert doc["photos"] == [PNG, PNG]
        # GET verify persistence
        lst = admin_client.get(f"{API}/reinterventions?client_id={client_id}", timeout=120).json()
        found = [x for x in lst if x["id"] == rid]
        assert found, "created reintervention not returned by GET"
        assert found[0]["photos"] == [PNG, PNG]
        assert found[0]["note"] == "TEST_iter179 photos"

    def test_create_without_photos_defaults_empty(self, admin_client, client_id):
        r = admin_client.post(f"{API}/reinterventions", json={
            "client_id": client_id, "scheduled_date": "2026-07-16", "note": "TEST_iter179 nophoto"}, timeout=120)
        assert r.status_code in (200, 201), r.text[:300]
        doc = r.json()
        TestReinterventionPhotos.created.append(doc["id"])
        assert doc["photos"] == []

    def test_update_photos(self, admin_client, client_id):
        r = admin_client.post(f"{API}/reinterventions", json={
            "client_id": client_id, "scheduled_date": "2026-07-17", "note": "TEST_iter179 upd"}, timeout=120)
        rid = r.json()["id"]
        TestReinterventionPhotos.created.append(rid)
        u = admin_client.put(f"{API}/reinterventions/{rid}", json={"photos": [PNG]}, timeout=120)
        assert u.status_code == 200, u.text[:300]
        lst = admin_client.get(f"{API}/reinterventions?client_id={client_id}", timeout=120).json()
        got = [x for x in lst if x["id"] == rid][0]
        assert got["photos"] == [PNG]

    def test_invalid_client_404(self, admin_client):
        r = admin_client.post(f"{API}/reinterventions", json={
            "client_id": "does-not-exist", "scheduled_date": "2026-07-18", "photos": [PNG]}, timeout=120)
        assert r.status_code == 404, r.status_code

    def test_invalid_date_422(self, admin_client, client_id):
        r = admin_client.post(f"{API}/reinterventions", json={
            "client_id": client_id, "scheduled_date": "15/07/2026"}, timeout=120)
        assert r.status_code == 422, r.status_code

    def test_delete_removes(self, admin_client, client_id):
        r = admin_client.post(f"{API}/reinterventions", json={
            "client_id": client_id, "scheduled_date": "2026-07-19", "photos": [PNG]}, timeout=120)
        rid = r.json()["id"]
        d = admin_client.delete(f"{API}/reinterventions/{rid}", timeout=60)
        assert d.status_code in (200, 204), d.status_code
        lst = admin_client.get(f"{API}/reinterventions?client_id={client_id}", timeout=120).json()
        assert not [x for x in lst if x["id"] == rid]


# ---------------- Regression: endpoints consumed by the frontend ----------------
class TestFrontendConsumedEndpoints:
    def test_get_clients_listing_exists(self, admin_client):
        """Clients.jsx and ReinterventionDialog.jsx both call GET /api/clients."""
        r = admin_client.get(f"{API}/clients", timeout=120)
        assert r.status_code == 200, f"GET /api/clients -> {r.status_code} {r.text[:200]}"
        assert isinstance(r.json(), list)
