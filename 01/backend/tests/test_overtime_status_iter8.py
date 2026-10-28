# Iteration 8 — Overtime pending/approved workflow + configurable monthly threshold alert
import pytest
import requests
from conftest import BASE_URL

MONTH = "2026-08"
TECH = "TEST_OT8"
TECH_H = "TEST_OT8_H"
TECH_T = "TEST_OT8_T"
D1 = f"{MONTH}-10"
D2 = f"{MONTH}-11"
D3 = f"{MONTH}-12"


def _clean(client, name=TECH):
    for d in (D1, D2, D3):
        client.post(f"{BASE_URL}/api/overtime", json={"technician_name": name, "date": d, "hours": 0}, timeout=30)


@pytest.fixture(scope="class")
def own_tech(request, admin_client):
    """Each test class works on its own technician name so xdist workers don't collide."""
    name = getattr(request.cls, "tech", TECH)
    _clean(admin_client, name)
    yield name
    _clean(admin_client, name)
    admin_client.put(f"{BASE_URL}/api/settings", json={"overtime_alert_threshold": 30}, timeout=30)


def _row(client, name=TECH, month=MONTH):
    d = client.get(f"{BASE_URL}/api/overtime?month={month}", timeout=30).json()
    return next((r for r in d["rows"] if r["technician_name"] == name), None), d


def _entry(client, date=D1, name=TECH, month=MONTH):
    d = client.get(f"{BASE_URL}/api/overtime?month={month}", timeout=30).json()
    return next((e for e in d["entries"] if e["technician_name"] == name and e["date"] == date), None)


class TestOvertimeStatusWorkflow:
    tech = TECH

    @pytest.fixture(scope="class", autouse=True)
    def _setup(self, own_tech):
        return own_tech

    def test_create_defaults_to_pending(self, admin_client):
        r = admin_client.post(f"{BASE_URL}/api/overtime", json={"technician_name": TECH, "date": D1, "hours": 4}, timeout=30)
        assert r.status_code == 200, r.text[:400]
        body = r.json()
        assert body["status"] == "pending", body
        assert "_id" not in body
        e = _entry(admin_client)
        assert e is not None and e["status"] == "pending" and e["hours"] == 4

    def test_row_breakdown_pending(self, admin_client):
        row, d = _row(admin_client)
        assert row["pending_hours"] == 4
        assert row["approved_hours"] == 0
        assert row["total_hours"] == 4
        assert row["over_threshold"] is False
        assert "threshold" in d

    def test_validate_sets_approved(self, admin_client):
        e = _entry(admin_client)
        r = admin_client.put(f"{BASE_URL}/api/overtime/{e['id']}/validate", timeout=30)
        assert r.status_code == 200, r.text[:400]
        body = r.json()
        assert body["status"] == "approved"
        assert body.get("validated_at")
        assert body.get("validated_by")
        assert "_id" not in body
        row, _ = _row(admin_client)
        assert row["approved_hours"] == 4 and row["pending_hours"] == 0

    def test_reject_sets_back_pending(self, admin_client):
        e = _entry(admin_client)
        r = admin_client.put(f"{BASE_URL}/api/overtime/{e['id']}/reject", timeout=30)
        assert r.status_code == 200, r.text[:400]
        body = r.json()
        assert body["status"] == "pending"
        assert body.get("validated_at") is None
        row, _ = _row(admin_client)
        assert row["pending_hours"] == 4 and row["approved_hours"] == 0

    def test_validate_unknown_id_404(self, admin_client):
        r = admin_client.put(f"{BASE_URL}/api/overtime/does-not-exist/validate", timeout=30)
        assert r.status_code == 404, r.status_code
        r = admin_client.put(f"{BASE_URL}/api/overtime/does-not-exist/reject", timeout=30)
        assert r.status_code == 404, r.status_code

    def test_validate_requires_auth(self, admin_client):
        e = _entry(admin_client)
        r = requests.put(f"{BASE_URL}/api/overtime/{e['id']}/validate", timeout=30)
        assert r.status_code in (401, 403), r.status_code

    def test_admin_edit_preserves_status(self, admin_client):
        e = _entry(admin_client)
        admin_client.put(f"{BASE_URL}/api/overtime/{e['id']}/validate", timeout=30)
        r = admin_client.post(f"{BASE_URL}/api/overtime", json={"technician_name": TECH, "date": D1, "hours": 6}, timeout=30)
        assert r.status_code == 200, r.text[:400]
        assert r.json()["status"] == "approved", "admin edit should preserve approved status"
        e2 = _entry(admin_client)
        assert e2["hours"] == 6 and e2["status"] == "approved"

    def test_bulk_validate_tech(self, admin_client):
        # add two pending entries
        admin_client.post(f"{BASE_URL}/api/overtime", json={"technician_name": TECH, "date": D2, "hours": 3}, timeout=30)
        admin_client.post(f"{BASE_URL}/api/overtime", json={"technician_name": TECH, "date": D3, "hours": 2}, timeout=30)
        row, _ = _row(admin_client)
        assert row["pending_hours"] == 5 and row["approved_hours"] == 6

        r = admin_client.post(f"{BASE_URL}/api/overtime/validate-tech", json={"technician_name": TECH, "month": MONTH}, timeout=30)
        assert r.status_code == 200, r.text[:400]
        body = r.json()
        assert body["validated"] == 2, body
        row, _ = _row(admin_client)
        assert row["pending_hours"] == 0 and row["approved_hours"] == 11

    def test_bulk_validate_missing_fields_400(self, admin_client):
        r = admin_client.post(f"{BASE_URL}/api/overtime/validate-tech", json={"technician_name": TECH}, timeout=30)
        assert r.status_code == 400, r.status_code

    def test_bulk_validate_requires_auth(self):
        r = requests.post(f"{BASE_URL}/api/overtime/validate-tech", json={"technician_name": TECH, "month": MONTH}, timeout=30)
        assert r.status_code in (401, 403), r.status_code


class TestOvertimeHardening:
    tech = TECH_H

    @pytest.fixture(scope="class", autouse=True)
    def _setup(self, own_tech):
        return own_tech

    def test_hours_above_24_rejected(self, admin_client):
        r = admin_client.post(f"{BASE_URL}/api/overtime", json={"technician_name": TECH_H, "date": D2, "hours": 99}, timeout=30)
        assert r.status_code == 422, f"{r.status_code} {r.text[:300]}"

    def test_negative_hours_rejected(self, admin_client):
        r = admin_client.post(f"{BASE_URL}/api/overtime", json={"technician_name": TECH_H, "date": D2, "hours": -1}, timeout=30)
        assert r.status_code == 422, r.status_code

    def test_invalid_date_rejected(self, admin_client):
        r = admin_client.post(f"{BASE_URL}/api/overtime", json={"technician_name": TECH_H, "date": "2026-13-45", "hours": 2}, timeout=30)
        assert r.status_code == 400, f"{r.status_code} {r.text[:300]}"
        assert "Date invalide" in r.text

    def test_valid_flow_unchanged(self, admin_client):
        r = admin_client.post(f"{BASE_URL}/api/overtime", json={"technician_name": TECH_H, "date": D2, "hours": 8}, timeout=30)
        assert r.status_code == 200, r.text[:300]
        assert r.json()["hours"] == 8
        admin_client.post(f"{BASE_URL}/api/overtime", json={"technician_name": TECH_H, "date": D2, "hours": 0}, timeout=30)


class TestOvertimeThreshold:
    tech = TECH_T

    @pytest.fixture(scope="class", autouse=True)
    def _setup(self, own_tech):
        return own_tech

    def test_settings_default_threshold_present(self, admin_client):
        r = admin_client.get(f"{BASE_URL}/api/settings", timeout=30)
        assert r.status_code == 200
        assert "overtime_alert_threshold" in r.json()

    def test_update_threshold_persists(self, admin_client):
        r = admin_client.put(f"{BASE_URL}/api/settings", json={"overtime_alert_threshold": 20}, timeout=30)
        assert r.status_code == 200, r.text[:300]
        assert r.json()["overtime_alert_threshold"] == 20
        g = admin_client.get(f"{BASE_URL}/api/settings", timeout=30).json()
        assert g["overtime_alert_threshold"] == 20

    def test_threshold_requires_admin(self):
        r = requests.put(f"{BASE_URL}/api/settings", json={"overtime_alert_threshold": 5}, timeout=30)
        assert r.status_code in (401, 403), r.status_code

    def test_over_threshold_flag(self, admin_client):
        # threshold=20; create 21h pending for TECH_T
        _clean(admin_client, TECH_T)
        admin_client.post(f"{BASE_URL}/api/overtime", json={"technician_name": TECH_T, "date": D1, "hours": 11}, timeout=30)
        admin_client.post(f"{BASE_URL}/api/overtime", json={"technician_name": TECH_T, "date": D2, "hours": 10}, timeout=30)
        row, d = _row(admin_client, TECH_T)
        assert d["threshold"] == 20
        assert row["total_hours"] == 21
        assert row["over_threshold"] is True

    def test_below_threshold_flag(self, admin_client):
        admin_client.put(f"{BASE_URL}/api/settings", json={"overtime_alert_threshold": 40}, timeout=30)
        row, d = _row(admin_client, TECH_T)
        assert d["threshold"] == 40
        assert row["over_threshold"] is False

    def test_threshold_zero_disables_alert(self, admin_client):
        r = admin_client.put(f"{BASE_URL}/api/settings", json={"overtime_alert_threshold": 0}, timeout=30)
        assert r.status_code == 200, r.text[:300]
        g = admin_client.get(f"{BASE_URL}/api/settings", timeout=30).json()
        assert g["overtime_alert_threshold"] == 0, "PUT with 0 must persist (None-filtering bug if it stays 40)"
        _, d = _row(admin_client, TECH_T)
        assert d["threshold"] == 0
        assert all(r2["over_threshold"] is False for r2 in d["rows"])

    def test_restore_threshold_30(self, admin_client):
        admin_client.put(f"{BASE_URL}/api/settings", json={"overtime_alert_threshold": 30}, timeout=30)
        g = admin_client.get(f"{BASE_URL}/api/settings", timeout=30).json()
        assert g["overtime_alert_threshold"] == 30


class TestRegressionPages:
    @pytest.mark.parametrize("path", [
        "/api/auth/me", "/api/sales", "/api/team", "/api/settings",
        "/api/reports/monthly?month=2026-08", "/api/commissions?month=2026-08",
        "/api/overtime?month=2026-08",
    ])
    def test_200(self, admin_client, path):
        r = admin_client.get(f"{BASE_URL}{path}", timeout=45)
        assert r.status_code == 200, f"{path} -> {r.status_code} {r.text[:200]}"
