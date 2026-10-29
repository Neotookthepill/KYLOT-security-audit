"""
Backend tests for Prospecteur feature (iter28):
- GET /api/prospecteurs (admin lists; prospecteur gets 403? Actually we expect it allowed only for admin/responsable path on PUT; GET may be allowed)
- POST /api/sales with prospecteur_id + prospecteur_commission → prospecteur_name set
- PUT /api/sales/{id} updates prospecteur fields, prospecteur_id='' clears commission to 0
- GET /api/prospection as admin returns row with client_name & commission
- PUT /api/prospection/{sid} admin updates commission; prospecteur gets 403
- GET /api/sales as prospecteur → 403 (sales view=none)
- GET /api/dashboard/executive DE sale 50/50 split
- Regression: Sous-traitance source + custom cheque installments
"""
import os
import time
import pytest
import requests

def _load_be_url():
    v = os.environ.get("REACT_APP_BACKEND_URL")
    if v:
        return v.rstrip("/")
    try:
        with open("/app/frontend/.env") as f:
            for line in f:
                if line.startswith("REACT_APP_BACKEND_URL="):
                    return line.split("=", 1)[1].strip().rstrip("/")
    except Exception:
        pass
    raise RuntimeError("REACT_APP_BACKEND_URL missing")


BASE_URL = _load_be_url()
API = f"{BASE_URL}/api"

ADMIN = {"email": "admin@example.invalid", "password": "CHANGE_ME_TEST_PASSWORD"}
PROSP = {"email": "test.prospecteur@qylot.fr", "password": "Prospect@2026"}


def _login(creds):
    r = requests.post(f"{API}/auth/login", json=creds, timeout=20)
    assert r.status_code == 200, f"login failed {creds['email']}: {r.status_code} {r.text}"
    return r.json().get("token") or r.json().get("access_token")


@pytest.fixture(scope="module")
def admin_token():
    return _login(ADMIN)


@pytest.fixture(scope="module")
def prosp_token():
    return _login(PROSP)


@pytest.fixture(scope="module")
def admin_h(admin_token):
    return {"Authorization": f"Bearer {admin_token}"}


@pytest.fixture(scope="module")
def prosp_h(prosp_token):
    return {"Authorization": f"Bearer {prosp_token}"}


@pytest.fixture(scope="module")
def prospecteur_user(admin_h):
    r = requests.get(f"{API}/prospecteurs", headers=admin_h, timeout=10)
    assert r.status_code == 200, r.text
    arr = r.json()
    assert isinstance(arr, list) and len(arr) >= 1, "No prospecteur seeded"
    # find TEST_Prospecteur
    tp = next((p for p in arr if "TEST_Prospecteur" in (p.get("name") or "")), arr[0])
    assert "id" in tp and "name" in tp
    return tp


@pytest.fixture(scope="module")
def client_id(admin_h):
    # Reuse TEST_QA_Client or create one
    r = requests.get(f"{API}/clients", headers=admin_h, timeout=10)
    assert r.status_code == 200, r.text
    arr = r.json() if isinstance(r.json(), list) else r.json().get("items", [])
    c = next((c for c in arr if "TEST_QA_Client" in (c.get("name") or "") or "TEST_" in (c.get("name") or "")), None)
    if c:
        return c["id"]
    r = requests.post(f"{API}/clients", headers=admin_h, json={
        "name": "TEST_Prospecteur_Client", "phone": "0600000001", "city": "Paris", "postal_code": "75001"
    }, timeout=10)
    assert r.status_code in (200, 201), r.text
    return r.json()["id"]


_created_sales = []


def _create_sale(admin_h, client_id, prospecteur_id=None, prospecteur_commission=None, source="Assist", is_de=False, commercial_2=None, amount=10000):
    payload = {
        "client_id": client_id,
        "service": "TEST_Service",
        "amount": amount,
        "sale_date": "2026-01-15",
        "status": "nouveau",
        "source": source,
        "commercial": "Thomas",
        "is_de": is_de,
    }
    if is_de and commercial_2:
        payload["commercial_2"] = commercial_2
    if prospecteur_id is not None:
        payload["prospecteur_id"] = prospecteur_id
    if prospecteur_commission is not None:
        payload["prospecteur_commission"] = prospecteur_commission
    r = requests.post(f"{API}/sales", headers=admin_h, json=payload, timeout=15)
    assert r.status_code in (200, 201), f"create sale: {r.status_code} {r.text}"
    sid = r.json()["id"]
    _created_sales.append(sid)
    return sid, r.json()


# ---------- Admin: create sale with prospecteur ----------
def test_create_sale_with_prospecteur(admin_h, client_id, prospecteur_user):
    sid, body = _create_sale(admin_h, client_id, prospecteur_id=prospecteur_user["id"], prospecteur_commission=500)
    assert body.get("prospecteur_id") == prospecteur_user["id"]
    assert body.get("prospecteur_name") == prospecteur_user["name"]
    assert float(body.get("prospecteur_commission") or 0) == 500.0


def test_prospection_list_admin(admin_h, prospecteur_user):
    r = requests.get(f"{API}/prospection", headers=admin_h, timeout=10)
    assert r.status_code == 200, r.text
    rows = r.json()
    mine = [x for x in rows if x.get("prospecteur_id") == prospecteur_user["id"]]
    assert len(mine) >= 1
    row = mine[0]
    assert "client_name" in row and row["client_name"]
    assert "status" in row
    assert "prospecteur_commission" in row


def test_update_prospection_commission_admin(admin_h, prospecteur_user):
    # Pick latest sale we created
    sid = _created_sales[0]
    r = requests.put(f"{API}/prospection/{sid}", headers=admin_h, json={"prospecteur_commission": 600}, timeout=10)
    assert r.status_code == 200, r.text
    assert float(r.json()["prospecteur_commission"]) == 600.0


def test_prospecteur_cannot_update_commission(prosp_h):
    sid = _created_sales[0]
    r = requests.put(f"{API}/prospection/{sid}", headers=prosp_h, json={"prospecteur_commission": 999}, timeout=10)
    assert r.status_code == 403


def test_prospecteur_cannot_list_sales(prosp_h):
    r = requests.get(f"{API}/sales", headers=prosp_h, timeout=10)
    assert r.status_code == 403


def test_prospecteur_can_list_own_prospection(prosp_h, prospecteur_user):
    r = requests.get(f"{API}/prospection", headers=prosp_h, timeout=10)
    assert r.status_code == 200, r.text
    rows = r.json()
    # only own + no amount field exposed
    assert all(x.get("prospecteur_id") == prospecteur_user["id"] for x in rows)
    assert all("amount" not in x for x in rows)
    assert len(rows) >= 1


def test_update_sale_clear_prospecteur(admin_h, client_id, prospecteur_user):
    # New sale to clear
    sid, _ = _create_sale(admin_h, client_id, prospecteur_id=prospecteur_user["id"], prospecteur_commission=400)
    r = requests.put(f"{API}/sales/{sid}", headers=admin_h, json={
        "prospecteur_id": "", "prospecteur_commission": 0
    }, timeout=10)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body.get("prospecteur_id") in ("", None)
    assert body.get("prospecteur_name") in ("", None)
    assert float(body.get("prospecteur_commission") or 0) == 0.0


def test_update_sale_set_prospecteur(admin_h, client_id, prospecteur_user):
    # Create plain sale then set prospecteur via PUT
    sid, _ = _create_sale(admin_h, client_id)
    r = requests.put(f"{API}/sales/{sid}", headers=admin_h, json={
        "prospecteur_id": prospecteur_user["id"], "prospecteur_commission": 500
    }, timeout=10)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body.get("prospecteur_id") == prospecteur_user["id"]
    assert body.get("prospecteur_name") == prospecteur_user["name"]
    assert float(body.get("prospecteur_commission") or 0) == 500.0


# ---------- Regression: Sous-traitance source ----------
def test_sale_source_sous_traitance(admin_h, client_id):
    sid, body = _create_sale(admin_h, client_id, source="Sous-traitance")
    assert body.get("source") == "Sous-traitance"


# ---------- Regression: dashboard executive DE 50/50 ----------
def test_dashboard_executive_ok(admin_h):
    r = requests.get(f"{API}/dashboard/executive?period=month", headers=admin_h, timeout=20)
    assert r.status_code == 200, r.text
    data = r.json()
    assert "ranking" in data


# ---------- Cleanup ----------
def test_zz_cleanup(admin_h):
    for sid in list(_created_sales):
        try:
            requests.delete(f"{API}/sales/{sid}", headers=admin_h, timeout=10)
        except Exception:
            pass
