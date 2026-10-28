"""Iteration 31 — regression after AIHelper.jsx hooks-hoist deploy fix.

Scope (per review request):
  - K8s probes: GET /health, GET /healthz (no auth, 200)
  - POST /api/auth/login (admin CHANGE_ME_TEST_PASSWORD)
  - GET /api/sales, /api/commissions, /api/bonuses
  - GET /api/project-bonuses/monthly?month=2026-08
  - POST /api/ai/action for the two frontend scenarios under test
      * "Vente Kilian 5000 chez Dupont" -> create_sale preview
      * "coucou"                        -> intent unknown (must NOT 500)
"""
import os

import pytest
import requests
from dotenv import dotenv_values

frontend_env = dotenv_values("/app/frontend/.env")
base_url = os.environ.get("REACT_APP_BACKEND_URL") or frontend_env.get("REACT_APP_BACKEND_URL")
if not base_url:
    raise RuntimeError("REACT_APP_BACKEND_URL missing from env and /app/frontend/.env")
BASE_URL = base_url.rstrip("/")
API = f"{BASE_URL}/api"

ADMIN_EMAIL = "admin@example.invalid"
ADMIN_PASSWORD = "CHANGE_ME_TEST_PASSWORD"


@pytest.fixture(scope="module")
def session():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


@pytest.fixture(scope="module")
def admin(session):
    r = session.post(f"{API}/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}, timeout=30)
    if r.status_code != 200:
        pytest.fail(f"Admin login failed {r.status_code}: {r.text[:400]}")
    token = r.json().get("token") or r.json().get("access_token")
    assert token, f"No token in login response: {r.json()}"
    c = requests.Session()
    c.headers.update({"Content-Type": "application/json", "Authorization": f"Bearer {token}"})
    return c


# --- K8s health probes -------------------------------------------------------
class TestHealthProbes:
    # NOTE: the K8s ingress routes every non-/api path to the frontend, so the public
    # URL returns index.html for /health. Liveness/readiness probes hit the backend
    # container port directly, which is what we assert here.
    @pytest.mark.parametrize("path", ["/health", "/healthz"])
    def test_probe_200_no_auth(self, session, path):
        r = session.get(f"http://localhost:8001{path}", timeout=20)
        assert r.status_code == 200, r.text[:300]
        assert r.json().get("status") in ("ok", "healthy", "up"), r.text[:200]


# --- Auth --------------------------------------------------------------------
class TestAuth:
    def test_login_success_shape(self, session):
        r = session.post(f"{API}/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}, timeout=30)
        assert r.status_code == 200, r.text[:300]
        d = r.json()
        token = d.get("token") or d.get("access_token")
        assert isinstance(token, str) and len(token) > 20
        user = d.get("user") or {}
        assert user.get("email") == ADMIN_EMAIL
        assert user.get("role") == "admin"

    def test_me_with_token(self, admin):
        r = admin.get(f"{API}/auth/me", timeout=20)
        assert r.status_code == 200, r.text[:300]
        d = r.json()
        assert d["email"] == ADMIN_EMAIL
        assert "_id" not in d, "Mongo _id leaked in /auth/me"

    def test_sales_requires_auth(self, session):
        r = session.get(f"{API}/sales", timeout=20)
        assert r.status_code in (401, 403), r.status_code


# --- Core read endpoints -----------------------------------------------------
class TestCoreReads:
    @pytest.mark.parametrize("path", ["/sales", "/commissions", "/bonuses"])
    def test_list_endpoints(self, admin, path):
        r = admin.get(f"{API}{path}", timeout=40)
        assert r.status_code == 200, f"{path} -> {r.status_code} {r.text[:300]}"
        d = r.json()
        items = d if isinstance(d, list) else (d.get("items") or d.get("data") or d)
        assert isinstance(items, (list, dict)), type(items)
        if isinstance(items, list) and items:
            assert "_id" not in items[0], f"Mongo _id leaked in {path}"

    def test_project_bonuses_monthly(self, admin):
        r = admin.get(f"{API}/project-bonuses/monthly", params={"month": "2026-08"}, timeout=40)
        assert r.status_code == 200, r.text[:300]
        d = r.json()
        assert isinstance(d, (list, dict)), type(d)
        if isinstance(d, list) and d:
            assert "_id" not in d[0]

    def test_project_bonuses_monthly_bad_format(self, admin):
        r = admin.get(f"{API}/project-bonuses/monthly", params={"month": "aout-2026"}, timeout=30)
        assert r.status_code in (400, 422), r.status_code


# --- AI action previews (backing the frontend flows under test) --------------
class TestAIActionPreviews:
    def test_create_sale_preview(self, admin):
        r = admin.post(f"{API}/ai/action", json={"message": "Vente Kilian 5000 chez Dupont"}, timeout=90)
        assert r.status_code == 200, r.text[:500]
        d = r.json()
        assert d.get("intent") == "create_sale", d
        assert isinstance(d.get("data"), dict)
        assert isinstance(d.get("missing"), list)
        assert (d["data"].get("client_name") or "").lower().startswith("dupont") or "dupont" in str(d["data"]).lower()

    def test_unknown_intent_preview(self, admin):
        r = admin.post(f"{API}/ai/action", json={"message": "coucou"}, timeout=90)
        assert r.status_code == 200, r.text[:500]
        d = r.json()
        assert d.get("intent") == "unknown", d
        # frontend ActionPreviewCard reads preview.missing unconditionally later on
        assert isinstance(d.get("missing", []), list)
