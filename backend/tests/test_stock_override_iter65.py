"""iter65 — Stock manual overrides (besoin / stock_previsionnel / reste_a_commander)."""
import os
import pytest
import requests
from dotenv import dotenv_values

fenv = dotenv_values("/app/frontend/.env")
BASE = (os.environ.get("REACT_APP_BACKEND_URL") or fenv.get("REACT_APP_BACKEND_URL")).rstrip("/")
API = f"{BASE}/api"

ADMIN = ("admin@example.invalid", "CHANGE_ME_TEST_PASSWORD")
COMM = ("test-comm@keylot.app", "Comm@2026")
TECH = ("test-tech@keylot.app", "Tech@2026")
PRODUCT = "TEST_Override_Iter65"


def _login(email, password):
    r = requests.post(f"{API}/auth/login", json={"email": email, "password": password}, timeout=30)
    if r.status_code != 200:
        pytest.fail(f"login {email} failed {r.status_code}: {r.text[:300]}")
    return r.json()["access_token"] if "access_token" in r.json() else r.json().get("token")


def _sess(token):
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json", "Authorization": f"Bearer {token}"})
    return s


@pytest.fixture(scope="module")
def admin():
    return _sess(_login(*ADMIN))


@pytest.fixture(scope="module")
def comm():
    return _sess(_login(*COMM))


@pytest.fixture(scope="module")
def tech():
    return _sess(_login(*TECH))


@pytest.fixture(scope="module")
def row(admin):
    r = admin.post(f"{API}/stock", json={"product_name": PRODUCT, "stock_disponible": 5, "commande_en_cours": 0}, timeout=30)
    assert r.status_code == 200, r.text
    doc = r.json()
    assert "_id" not in doc
    yield doc
    admin.delete(f"{API}/stock/{doc['id']}", timeout=30)


def _get_row(sess, key):
    r = sess.get(f"{API}/stock", timeout=30)
    assert r.status_code == 200, r.text
    data = r.json()
    items = data.get("items") if isinstance(data, dict) else data
    for it in items:
        if it.get("product_key") == key.lower():
            return it
    return None


class TestOverrideCrud:
    def test_set_besoin_override(self, admin, row):
        r = admin.put(f"{API}/stock/{row['id']}/override", json={"field": "besoin", "value": 42}, timeout=30)
        assert r.status_code == 200, r.text
        ov = r.json()["manual_overrides"]["besoin"]
        assert ov["value"] == 42
        assert ov["updated_by"] and ov["updated_by_name"] and ov["updated_at"]
        assert "_id" not in r.json()

    def test_get_reflects_override(self, admin, row):
        it = _get_row(admin, PRODUCT)
        assert it is not None
        assert it["besoin"] == 42
        assert it["besoin_auto"] == 0
        assert it["manual_overrides"]["besoin"]["value"] == 42

    def test_besoin_override_cascades_to_derived_columns(self, admin, row):
        """BUG iter65: reste_a_commander / stock_previsionnel auto are computed from
        besoin_auto, so a manual besoin override never affects the derived columns."""
        it = _get_row(admin, PRODUCT)
        assert it["besoin"] == 42 and it["stock_disponible"] == 5
        assert it["reste_a_commander"] == 37, f"expected max(0,42-5-0)=37, got {it['reste_a_commander']}"
        assert it["stock_previsionnel"] == -37
        assert it["status"] == "red"

    def test_override_prev_and_reste(self, admin, row):
        assert admin.put(f"{API}/stock/{row['id']}/override", json={"field": "stock_previsionnel", "value": -7}, timeout=30).status_code == 200
        assert admin.put(f"{API}/stock/{row['id']}/override", json={"field": "reste_a_commander", "value": 0}, timeout=30).status_code == 200
        it = _get_row(admin, PRODUCT)
        assert it["stock_previsionnel"] == -7
        assert it["reste_a_commander"] == 0
        assert it["status"] != "red"
        # set reste > 0 -> red
        admin.put(f"{API}/stock/{row['id']}/override", json={"field": "reste_a_commander", "value": 3}, timeout=30)
        it = _get_row(admin, PRODUCT)
        assert it["reste_a_commander"] == 3 and it["status"] == "red"

    def test_persists_after_upsert(self, admin, row):
        r = admin.post(f"{API}/stock", json={"product_name": PRODUCT, "stock_disponible": 11}, timeout=30)
        assert r.status_code == 200, r.text
        it = _get_row(admin, PRODUCT)
        assert it["stock_disponible"] == 11
        assert it["manual_overrides"]["besoin"]["value"] == 42
        assert it["besoin"] == 42

    def test_delete_override(self, admin, row):
        for f in ("stock_previsionnel", "reste_a_commander"):
            assert admin.delete(f"{API}/stock/{row['id']}/override/{f}", timeout=30).status_code == 200
        r = admin.delete(f"{API}/stock/{row['id']}/override/besoin", timeout=30)
        assert r.status_code == 200, r.text
        assert r.json().get("manual_overrides") == {}
        it = _get_row(admin, PRODUCT)
        assert it["manual_overrides"] == {}
        assert it["besoin"] == it["besoin_auto"]


class TestValidationAndRbac:
    def test_invalid_field_rejected(self, admin, row):
        r = admin.put(f"{API}/stock/{row['id']}/override", json={"field": "stock_disponible", "value": 5}, timeout=30)
        assert r.status_code == 422, f"expected 422, got {r.status_code}: {r.text[:200]}"

    def test_out_of_range_value_rejected(self, admin, row):
        r = admin.put(f"{API}/stock/{row['id']}/override", json={"field": "besoin", "value": 999999}, timeout=30)
        assert r.status_code == 422

    def test_delete_invalid_field(self, admin, row):
        r = admin.delete(f"{API}/stock/{row['id']}/override/foo", timeout=30)
        assert r.status_code == 400

    def test_unknown_row_404(self, admin):
        r = admin.put(f"{API}/stock/does-not-exist/override", json={"field": "besoin", "value": 1}, timeout=30)
        assert r.status_code == 404

    def test_commercial_forbidden(self, comm, row):
        r = comm.put(f"{API}/stock/{row['id']}/override", json={"field": "besoin", "value": 9}, timeout=30)
        assert r.status_code == 403, r.text
        r2 = comm.delete(f"{API}/stock/{row['id']}/override/besoin", timeout=30)
        assert r2.status_code == 403

    def test_technicien_forbidden(self, tech, row):
        r = tech.put(f"{API}/stock/{row['id']}/override", json={"field": "besoin", "value": 9}, timeout=30)
        assert r.status_code == 403, r.text
        r2 = tech.delete(f"{API}/stock/{row['id']}/override/besoin", timeout=30)
        assert r2.status_code == 403

    def test_unauthenticated(self, row):
        r = requests.put(f"{API}/stock/{row['id']}/override", json={"field": "besoin", "value": 1}, timeout=30)
        assert r.status_code in (401, 403)
