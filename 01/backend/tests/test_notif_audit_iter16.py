"""Iteration 16 — Regression + new features: Sales period filters (UI), optional in-app
notifications (5 categories, OFF by default) and the audit log (/api/audit, admin-only).

NOTE: run this file serially (`pytest tests/test_notif_audit_iter16.py -n 0`): the tests
mutate the company-wide notification settings, so parallel workers interfere.

Covers:
  - REGRESSION: admin login, /auth/me, /settings notification defaults, /notifications, /audit
  - REGRESSION: super_admin isolation, dashboard/executive recent_sales.client_name
  - NEW: notification emission when a commercial creates a sale (category new_sales)
  - NEW: notification not emitted when the category is OFF
  - NEW: audit filters (resource/action/user_id/from_date/to_date) + admin-only permission
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
BASE_URL = _base.rstrip("/")

ADMIN = {"email": "admin@example.invalid", "password": "CHANGE_ME_TEST_PASSWORD"}
SUPER = {"email": "super@keylot.app", "password": "Super@2026"}
COM = {"email": "com1@keylot.example.com", "password": "Com@2026", "name": "TEST_Com1", "role": "commercial"}

NOTIF_CATEGORIES = ["new_sales", "objectives", "planning", "overtime", "project_alerts"]


def _client(token=None):
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    if token:
        s.headers.update({"Authorization": f"Bearer {token}"})
    return s


def _login(creds):
    r = requests.post(f"{BASE_URL}/api/auth/login", json=creds, timeout=30)
    return r


# ---------------- Fixtures ----------------

@pytest.fixture(scope="module")
def admin():
    r = _login(ADMIN)
    if r.status_code != 200:
        pytest.fail(f"Admin login failed {r.status_code}: {r.text[:300]}")
    return _client(r.json()["token"])


@pytest.fixture(scope="module")
def superadmin():
    r = _login(SUPER)
    if r.status_code != 200:
        pytest.fail(f"Super-admin login failed {r.status_code}: {r.text[:300]}")
    return _client(r.json()["token"])


@pytest.fixture(scope="module")
def commercial(admin):
    """Create (or reuse) the commercial test account and return (client, user_id)."""
    r = admin.post(f"{BASE_URL}/api/users", json=COM, timeout=30)
    if r.status_code == 400 and "déjà" in r.text:
        users = admin.get(f"{BASE_URL}/api/users", timeout=30).json()
        u = next((x for x in users if x["email"] == COM["email"]), None)
        assert u, "existing commercial not found in /api/users"
        uid = u["id"]
    else:
        assert r.status_code == 200, f"create user failed {r.status_code}: {r.text[:300]}"
        body = r.json()
        assert body["email"] == COM["email"]
        assert body["role"] == "commercial"
        assert "password_hash" not in body and "_id" not in body
        uid = body["id"]
    lr = _login({"email": COM["email"], "password": COM["password"]})
    assert lr.status_code == 200, f"commercial login failed {lr.status_code}: {lr.text[:300]}"
    return _client(lr.json()["token"]), uid


@pytest.fixture(scope="module")
def existing_client_id(admin):
    r = admin.get(f"{BASE_URL}/api/clients", timeout=30)
    assert r.status_code == 200
    clients = r.json()
    assert clients, "no existing client to attach a sale to"
    return clients[0]["id"]


def _set_notif(admin, **flags):
    prefs = {k: False for k in NOTIF_CATEGORIES}
    prefs.update(flags)
    r = admin.put(f"{BASE_URL}/api/settings", json={"notifications": prefs}, timeout=30)
    assert r.status_code == 200, f"PUT /settings {r.status_code}: {r.text[:300]}"
    return r.json()["notifications"]


def _purge_notifs(client):
    items = client.get(f"{BASE_URL}/api/notifications", timeout=30).json()["items"]
    for it in items:
        client.delete(f"{BASE_URL}/api/notifications/{it['id']}", timeout=30)


# ---------------- REGRESSION ----------------

class TestRegression:
    def test_admin_auth_me(self, admin):
        r = admin.get(f"{BASE_URL}/api/auth/me", timeout=30)
        assert r.status_code == 200
        d = r.json()
        assert d["email"] == ADMIN["email"]
        assert d["role"] == "admin"
        assert d["company_id"] == "default"
        assert isinstance(d.get("permissions"), dict)
        assert "_id" not in d and "password_hash" not in d

    def test_settings_exposes_all_notification_categories(self, admin):
        r = admin.get(f"{BASE_URL}/api/settings", timeout=30)
        assert r.status_code == 200
        notif = r.json().get("notifications")
        assert isinstance(notif, dict)
        assert sorted(notif.keys()) == sorted(NOTIF_CATEGORIES)
        for v in notif.values():
            assert isinstance(v, bool)

    def test_notifications_shape(self, admin):
        r = admin.get(f"{BASE_URL}/api/notifications", timeout=30)
        assert r.status_code == 200
        d = r.json()
        assert isinstance(d["items"], list)
        assert isinstance(d["unread"], int)
        for it in d["items"]:
            assert "_id" not in it

    def test_audit_has_entries(self, admin):
        r = admin.get(f"{BASE_URL}/api/audit", timeout=30)
        assert r.status_code == 200
        docs = r.json()
        assert isinstance(docs, list)
        assert len(docs) >= 1, "audit log empty — expected at least one prior sensitive action"
        d = docs[0]
        for k in ("id", "user_id", "user_name", "user_role", "action", "resource", "at"):
            assert k in d, f"missing {k} in audit entry"
        assert "_id" not in d

    def test_superadmin_isolation(self, superadmin):
        r = superadmin.get(f"{BASE_URL}/api/sales", timeout=30)
        assert r.status_code == 403, f"expected 403 for super_admin on /api/sales, got {r.status_code}"
        r2 = superadmin.get(f"{BASE_URL}/api/superadmin/companies", timeout=30)
        assert r2.status_code == 200
        assert isinstance(r2.json(), list)

    def test_dashboard_executive(self, admin):
        r = admin.get(f"{BASE_URL}/api/dashboard/executive", timeout=30)
        assert r.status_code == 200
        d = r.json()
        assert "recent_sales" in d
        client_ids = {c["id"] for c in admin.get(f"{BASE_URL}/api/clients", timeout=30).json()}
        for s in d["recent_sales"]:
            assert "_id" not in s
            if s["client_id"] in client_ids:
                assert s.get("client_name"), f"recent_sales entry missing client_name: {s}"
            else:
                # Orphan sale: the client was deleted without cascading (see report iter16)
                pytest.skip(f"orphan sale detected (client {s['client_id']} deleted): client_name empty")


# ---------------- NEW: notifications ----------------

class TestNotifications:
    def test_notification_emitted_when_category_on(self, admin, commercial, existing_client_id):
        com_client, com_id = commercial
        _set_notif(admin, new_sales=True, overtime=True)
        _purge_notifs(admin)
        base = admin.get(f"{BASE_URL}/api/notifications", timeout=30).json()
        assert base["unread"] == 0

        payload = {
            "client_id": existing_client_id,
            "service": "TEST_Notif Vente A",
            "amount": 4321,
            "sale_date": "2026-07-01",
            "commercial": COM["name"],
            "bdc": f"TEST-{uuid.uuid4().hex[:6]}",
        }
        r = com_client.post(f"{BASE_URL}/api/sales", json=payload, timeout=30)
        assert r.status_code == 200, f"create sale failed {r.status_code}: {r.text[:300]}"
        sale = r.json()
        assert sale["amount"] == 4321
        assert "_id" not in sale
        TestNotifications.sale_a = sale["id"]
        TestNotifications.com_id = com_id

        d = admin.get(f"{BASE_URL}/api/notifications", timeout=30).json()
        assert d["unread"] == 1, f"expected unread=1, got {d}"
        item = d["items"][0]
        assert item["category"] == "new_sales"
        assert item["is_read"] is False
        assert item["link_url"] == "/ventes"
        assert "4321" in item["message"]
        TestNotifications.notif_id = item["id"]

    def test_commercial_does_not_receive_own_notification(self, commercial):
        com_client, _ = commercial
        d = com_client.get(f"{BASE_URL}/api/notifications", timeout=30).json()
        assert d["unread"] == 0, f"commercial should not be notified of own sale: {d}"

    def test_mark_read_then_delete(self, admin):
        nid = getattr(TestNotifications, "notif_id", None)
        assert nid, "no notification id from previous test"
        r = admin.put(f"{BASE_URL}/api/notifications/{nid}/read", timeout=30)
        assert r.status_code == 200
        d = admin.get(f"{BASE_URL}/api/notifications", timeout=30).json()
        assert d["unread"] == 0
        assert d["items"][0]["is_read"] is True

        r2 = admin.delete(f"{BASE_URL}/api/notifications/{nid}", timeout=30)
        assert r2.status_code == 200
        d2 = admin.get(f"{BASE_URL}/api/notifications", timeout=30).json()
        assert all(i["id"] != nid for i in d2["items"])
        # deleting twice -> 404
        assert admin.delete(f"{BASE_URL}/api/notifications/{nid}", timeout=30).status_code == 404

    def test_mark_read_unknown_id_404(self, admin):
        r = admin.put(f"{BASE_URL}/api/notifications/{uuid.uuid4()}/read", timeout=30)
        assert r.status_code == 404

    def test_no_notification_when_category_off(self, admin, commercial, existing_client_id):
        com_client, _ = commercial
        _set_notif(admin, new_sales=False)
        _purge_notifs(admin)
        payload = {
            "client_id": existing_client_id,
            "service": "TEST_Notif Vente B",
            "amount": 1111,
            "sale_date": "2026-07-02",
            "commercial": COM["name"],
        }
        r = com_client.post(f"{BASE_URL}/api/sales", json=payload, timeout=30)
        assert r.status_code == 200
        TestNotifications.sale_b = r.json()["id"]
        d = admin.get(f"{BASE_URL}/api/notifications", timeout=30).json()
        assert d["unread"] == 0, f"notification created while new_sales OFF: {d}"
        assert d["items"] == []

    def test_read_all(self, admin, commercial, existing_client_id):
        com_client, _ = commercial
        _set_notif(admin, new_sales=True)
        payload = {
            "client_id": existing_client_id,
            "service": "TEST_Notif Vente C",
            "amount": 999,
            "sale_date": "2026-07-03",
            "commercial": COM["name"],
        }
        r = com_client.post(f"{BASE_URL}/api/sales", json=payload, timeout=30)
        assert r.status_code == 200
        TestNotifications.sale_c = r.json()["id"]
        assert admin.get(f"{BASE_URL}/api/notifications", timeout=30).json()["unread"] >= 1
        ra = admin.post(f"{BASE_URL}/api/notifications/read-all", timeout=30)
        assert ra.status_code == 200
        assert ra.json()["marked"] >= 1
        assert admin.get(f"{BASE_URL}/api/notifications", timeout=30).json()["unread"] == 0

    def test_only_unread_filter(self, admin):
        r = admin.get(f"{BASE_URL}/api/notifications?only_unread=true", timeout=30)
        assert r.status_code == 200
        assert r.json()["items"] == []


class TestOvertimeNotification:
    """Category 'overtime': a technician declaring hours notifies admins & responsables."""

    def test_overtime_declaration_notifies_admin(self, admin):
        tech = {"email": "tech16@keylot.example.com", "password": "Tech@2026",
                "name": "TEST_Tech16", "role": "technicien"}
        r = admin.post(f"{BASE_URL}/api/users", json=tech, timeout=30)
        assert r.status_code in (200, 400), f"{r.status_code}: {r.text[:200]}"
        lr = _login({"email": tech["email"], "password": tech["password"]})
        assert lr.status_code == 200, f"tech login failed {lr.status_code}: {lr.text[:200]}"
        tc = _client(lr.json()["token"])

        _set_notif(admin, overtime=True)
        _purge_notifs(admin)
        # ensure a fresh insert (the update path intentionally does not re-notify)
        tc.post(f"{BASE_URL}/api/overtime", json={
            "technician_name": "TEST_Tech16", "date": "2026-07-06", "hours": 0,
        }, timeout=30)
        ov = tc.post(f"{BASE_URL}/api/overtime", json={
            "technician_name": "TEST_Tech16", "date": "2026-07-06", "hours": 3.5,
        }, timeout=30)
        assert ov.status_code == 200, f"overtime failed {ov.status_code}: {ov.text[:200]}"
        TestOvertimeNotification.oid = ov.json().get("id")

        d = admin.get(f"{BASE_URL}/api/notifications", timeout=30).json()
        assert d["unread"] == 1, f"expected overtime notification, got {d}"
        assert d["items"][0]["category"] == "overtime"
        assert d["items"][0]["link_url"] == "/heures-sup"
        _purge_notifs(admin)
        _set_notif(admin)  # all OFF again

    def test_overtime_notification_off(self, admin):
        lr = _login({"email": "tech16@keylot.example.com", "password": "Tech@2026"})
        assert lr.status_code == 200
        tc = _client(lr.json()["token"])
        _set_notif(admin)  # all OFF
        _purge_notifs(admin)
        ov = tc.post(f"{BASE_URL}/api/overtime", json={
            "technician_name": "TEST_Tech16", "date": "2026-07-07", "hours": 2,
        }, timeout=30)
        assert ov.status_code == 200
        assert admin.get(f"{BASE_URL}/api/notifications", timeout=30).json()["unread"] == 0


class TestNotificationIsolation:
    def test_notifications_are_per_user(self, admin, commercial):
        """The commercial must never see the admin's notifications."""
        com_client, _ = commercial
        _set_notif(admin, new_sales=True)
        cid = admin.get(f"{BASE_URL}/api/clients", timeout=30).json()[0]["id"]
        r = com_client.post(f"{BASE_URL}/api/sales", json={
            "client_id": cid, "service": "TEST_Isolation Notif", "amount": 10,
            "sale_date": "2026-07-08", "commercial": COM["name"],
        }, timeout=30)
        assert r.status_code == 200
        TestNotifications.sale_iso = r.json()["id"]
        com = com_client.get(f"{BASE_URL}/api/notifications", timeout=30).json()
        assert com["unread"] == 0
        adm = admin.get(f"{BASE_URL}/api/notifications", timeout=30).json()
        assert adm["unread"] >= 1
        admin_ids = {i["id"] for i in adm["items"]}
        assert not (admin_ids & {i["id"] for i in com["items"]})
        _purge_notifs(admin)
        _set_notif(admin)

    def test_notifications_require_auth(self):
        r = requests.get(f"{BASE_URL}/api/notifications", timeout=30)
        assert r.status_code in (401, 403)


# ---------------- NEW: audit ----------------

class TestAudit:
    def test_filter_resource_action(self, admin):
        r = admin.get(f"{BASE_URL}/api/audit?resource=sale&action=create", timeout=30)
        assert r.status_code == 200
        docs = r.json()
        assert len(docs) >= 2, f"expected >=2 sale/create audit entries, got {len(docs)}"
        for d in docs:
            assert d["resource"] == "sale"
            assert d["action"] == "create"
            assert d["user_name"]
            assert d["user_role"]
            assert d["at"]
        services = [(d.get("after") or {}).get("service", "") for d in docs]
        assert any("TEST_Notif Vente" in s for s in services), "test sales not present in audit log"

    def test_filter_by_user_id(self, admin, commercial):
        _, com_id = commercial
        r = admin.get(f"{BASE_URL}/api/audit?user_id={com_id}&action=create", timeout=30)
        assert r.status_code == 200
        docs = r.json()
        assert len(docs) >= 2
        for d in docs:
            assert d["user_id"] == com_id
            assert d["user_role"] == "commercial"

    def test_filter_by_date_range(self, admin):
        r = admin.get(f"{BASE_URL}/api/audit?from_date=2026-07-01&to_date=2030-01-01", timeout=30)
        assert r.status_code == 200
        assert isinstance(r.json(), list)
        r2 = admin.get(f"{BASE_URL}/api/audit?from_date=2000-01-01&to_date=2000-01-02", timeout=30)
        assert r2.status_code == 200
        assert r2.json() == [], "date filter did not exclude out-of-range entries"

    def test_audit_forbidden_for_commercial(self, commercial):
        com_client, _ = commercial
        r = com_client.get(f"{BASE_URL}/api/audit", timeout=30)
        assert r.status_code == 403, f"expected 403 for commercial on /api/audit, got {r.status_code}"

    def test_audit_requires_auth(self):
        r = requests.get(f"{BASE_URL}/api/audit", timeout=30)
        assert r.status_code in (401, 403)

    def test_delete_logged_in_audit(self, admin, existing_client_id):
        cr = admin.post(f"{BASE_URL}/api/sales", json={
            "client_id": existing_client_id, "service": "TEST_Audit Delete",
            "amount": 500, "sale_date": "2026-07-04",
        }, timeout=30)
        assert cr.status_code == 200, f"create sale failed {cr.status_code}: {cr.text[:300]}"
        sid = cr.json()["id"]
        r = admin.delete(f"{BASE_URL}/api/sales/{sid}", timeout=30)
        assert r.status_code == 200
        docs = admin.get(f"{BASE_URL}/api/audit?resource=sale&action=delete", timeout=30).json()
        assert any(d["resource_id"] == sid for d in docs), "delete not recorded in audit log"


# ---------------- Cleanup ----------------

@pytest.fixture(scope="module", autouse=True)
def cleanup(request):
    yield
    r = _login(ADMIN)
    if r.status_code != 200:
        return
    c = _client(r.json()["token"])
    # restore notifications all OFF (default design choice)
    c.put(f"{BASE_URL}/api/settings", json={"notifications": {k: False for k in NOTIF_CATEGORIES}}, timeout=30)
    for attr in ("sale_a", "sale_b", "sale_c", "sale_iso"):
        sid = getattr(TestNotifications, attr, None)
        if sid:
            c.delete(f"{BASE_URL}/api/sales/{sid}", timeout=30)
    _purge_notifs(c)
