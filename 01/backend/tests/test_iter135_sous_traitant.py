"""iter135 : POST /api/team accepte type='sous_traitant' sans email."""
import os
import uuid

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
    s.headers.update({"Content-Type": "application/json"})
    r = s.post(f"{BASE_URL}/api/auth/login", json=ADMIN, timeout=30)
    if r.status_code != 200:
        pytest.fail(f"Admin login failed {r.status_code}: {r.text[:300]}")
    token = r.json().get("access_token") or r.json().get("token")
    if not token:
        pytest.fail(f"No token in login response: {r.text[:300]}")
    s.headers.update({"Authorization": f"Bearer {token}"})
    return s


@pytest.fixture(scope="module")
def created_ids():
    ids = []
    yield ids


@pytest.fixture(scope="module", autouse=True)
def cleanup(admin_client, created_ids):
    yield
    for tid in created_ids:
        admin_client.delete(f"{BASE_URL}/api/team/{tid}", timeout=30)


class TestSousTraitantTeam:
    def test_create_sous_traitant_without_email(self, admin_client, created_ids):
        name = f"TEST_ST_{uuid.uuid4().hex[:6]}"
        r = admin_client.post(f"{BASE_URL}/api/team", json={"name": name, "type": "sous_traitant"}, timeout=30)
        assert r.status_code == 200, r.text[:400]
        d = r.json()
        assert d["name"] == name
        assert d["type"] == "sous_traitant"
        assert d.get("email") == ""
        assert isinstance(d.get("id"), str)
        assert "_id" not in d
        created_ids.append(d["id"])

        # persistence via GET /team?type=sous_traitant
        g = admin_client.get(f"{BASE_URL}/api/team?type=sous_traitant", timeout=30)
        assert g.status_code == 200
        names = [m["name"] for m in g.json()]
        assert name in names

    def test_duplicate_rejected(self, admin_client, created_ids):
        name = f"TEST_ST_DUP_{uuid.uuid4().hex[:6]}"
        r1 = admin_client.post(f"{BASE_URL}/api/team", json={"name": name, "type": "sous_traitant"}, timeout=30)
        assert r1.status_code == 200
        created_ids.append(r1.json()["id"])
        r2 = admin_client.post(f"{BASE_URL}/api/team", json={"name": name, "type": "sous_traitant"}, timeout=30)
        assert r2.status_code == 400
        assert "existant" in r2.json().get("detail", "").lower()

    def test_invalid_type_rejected(self, admin_client):
        r = admin_client.post(f"{BASE_URL}/api/team", json={"name": "TEST_ST_BAD", "type": "plombier"}, timeout=30)
        assert r.status_code in (400, 422), r.text[:300]

    def test_empty_name_rejected(self, admin_client):
        r = admin_client.post(f"{BASE_URL}/api/team", json={"name": "   ", "type": "sous_traitant"}, timeout=30)
        assert r.status_code in (400, 422)

    def test_with_email_persisted(self, admin_client, created_ids):
        name = f"TEST_ST_MAIL_{uuid.uuid4().hex[:6]}"
        email = f"{name.lower()}@keylot.test"
        r = admin_client.post(f"{BASE_URL}/api/team", json={"name": name, "type": "sous_traitant", "email": email}, timeout=30)
        assert r.status_code == 200, r.text[:300]
        created_ids.append(r.json()["id"])
        assert r.json()["email"] == email.lower()

    def test_delete_removes(self, admin_client):
        name = f"TEST_ST_DEL_{uuid.uuid4().hex[:6]}"
        r = admin_client.post(f"{BASE_URL}/api/team", json={"name": name, "type": "sous_traitant"}, timeout=30)
        tid = r.json()["id"]
        d = admin_client.delete(f"{BASE_URL}/api/team/{tid}", timeout=30)
        assert d.status_code in (200, 204), d.text[:300]
        g = admin_client.get(f"{BASE_URL}/api/team?type=sous_traitant", timeout=30)
        assert name not in [m["name"] for m in g.json()]

    def test_non_admin_forbidden(self):
        s = requests.Session()
        r = s.post(f"{BASE_URL}/api/auth/login", json={"email": "test-tech@keylot.app", "password": "Tech@2026"}, timeout=30)
        if r.status_code != 200:
            pytest.skip("technicien test account unavailable")
        token = r.json().get("access_token") or r.json().get("token")
        s.headers.update({"Authorization": f"Bearer {token}"})
        resp = s.post(f"{BASE_URL}/api/team", json={"name": "TEST_ST_FORBID", "type": "sous_traitant"}, timeout=30)
        assert resp.status_code in (401, 403), resp.text[:300]
