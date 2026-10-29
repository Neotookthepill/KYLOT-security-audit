"""Iteration 4 — PUT /api/team/{id} objectif update + persistence (Sales 'CA par commercial' inline edit backend)."""
import os
import pytest
import requests
from dotenv import dotenv_values

frontend_env = dotenv_values("/app/frontend/.env")
base_url = os.environ.get("REACT_APP_BACKEND_URL") or frontend_env.get("REACT_APP_BACKEND_URL")
if not base_url:
    raise RuntimeError("REACT_APP_BACKEND_URL missing")
BASE_URL = base_url.rstrip("/")

ADMIN = {"email": "admin@example.invalid", "password": "CHANGE_ME_TEST_PASSWORD"}


@pytest.fixture(scope="module")
def admin_client():
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/login", json=ADMIN, timeout=30)
    if r.status_code != 200:
        pytest.fail(f"Admin login failed {r.status_code}: {r.text[:300]}")
    token = r.json().get("token") or r.json().get("access_token")
    assert token, f"no token in {r.json()}"
    s.headers.update({"Authorization": f"Bearer {token}", "Content-Type": "application/json"})
    return s


def test_list_commerciaux_shape(admin_client):
    r = admin_client.get(f"{BASE_URL}/api/team?type=commercial", timeout=30)
    assert r.status_code == 200
    data = r.json()
    assert isinstance(data, list) and len(data) > 0
    for m in data:
        assert "id" in m and isinstance(m["id"], str)
        assert "name" in m
        assert "_id" not in m
        assert "objectif" in m


def test_update_objectif_persists_and_restore(admin_client):
    members = admin_client.get(f"{BASE_URL}/api/team?type=commercial", timeout=30).json()
    # pick a member with objectif 0 if possible
    target = next((m for m in members if not m.get("objectif")), members[0])
    original = target.get("objectif") or 0
    try:
        r = admin_client.put(f"{BASE_URL}/api/team/{target['id']}", json={"objectif": 20000}, timeout=30)
        assert r.status_code == 200, r.text[:300]
        body = r.json()
        assert body.get("objectif") == 20000
        assert "_id" not in body
        # verify persistence via GET
        again = admin_client.get(f"{BASE_URL}/api/team?type=commercial", timeout=30).json()
        found = next(m for m in again if m["id"] == target["id"])
        assert found["objectif"] == 20000
        assert found["name"] == target["name"]  # other fields intact
    finally:
        admin_client.put(f"{BASE_URL}/api/team/{target['id']}", json={"objectif": original}, timeout=30)
        after = admin_client.get(f"{BASE_URL}/api/team?type=commercial", timeout=30).json()
        assert next(m for m in after if m["id"] == target["id"]).get("objectif", 0) == original


def test_update_objectif_requires_auth(admin_client):
    members = admin_client.get(f"{BASE_URL}/api/team?type=commercial", timeout=30).json()
    r = requests.put(f"{BASE_URL}/api/team/{members[0]['id']}", json={"objectif": 999}, timeout=30)
    assert r.status_code in (401, 403), r.status_code


def test_update_objectif_unknown_id(admin_client):
    r = admin_client.put(f"{BASE_URL}/api/team/does-not-exist-xyz", json={"objectif": 100}, timeout=30)
    assert r.status_code == 404, f"{r.status_code} {r.text[:200]}"


def test_settings_objectif_ca_still_works(admin_client):
    r = admin_client.get(f"{BASE_URL}/api/settings", timeout=30)
    assert r.status_code == 200
    assert "objectif_ca" in r.json()


def test_sales_list_ok(admin_client):
    r = admin_client.get(f"{BASE_URL}/api/sales", timeout=30)
    assert r.status_code == 200
    assert isinstance(r.json(), list)
