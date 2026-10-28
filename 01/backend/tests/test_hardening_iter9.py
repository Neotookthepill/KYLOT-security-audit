"""Iteration 9 — backend hardening checks (settings bounds, validate-tech Pydantic model + month check)."""
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


@pytest.fixture(scope="module")
def creds():
    content = Path("/app/memory/test_credentials.md").read_text(encoding="utf-8")
    _m = re.search(r'(?is)^##\s*(?:Default company admin|Admin\b).*?(?=^##\s|\Z)', content, re.M)
    if _m:
        content = _m.group(0)  # skip the super-admin block (403 on tenant endpoints)
    e = re.search(r'(?im)^\s*(?:[-*]\s*)?(?:\*\*)?email(?:\*\*)?\s*:\s*`?([^`\s]+)', content)
    p = re.search(r'(?im)^\s*(?:[-*]\s*)?(?:\*\*)?password(?:\*\*)?\s*:\s*`?([^`\s]+)', content)
    if not e or not p:
        pytest.skip("credentials missing")
    return {"email": e.group(1), "password": p.group(1)}


@pytest.fixture(scope="module")
def client(creds):
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    r = s.post(f"{API}/auth/login", json=creds, timeout=30)
    if r.status_code != 200:
        pytest.fail(f"login failed {r.status_code}: {r.text[:300]}")
    token = r.json().get("token") or r.json().get("access_token")
    if not token:
        pytest.fail(f"no token in login response: {r.text[:300]}")
    s.headers.update({"Authorization": f"Bearer {token}"})
    yield s
    # always restore threshold
    s.put(f"{API}/settings", json={"overtime_alert_threshold": 30}, timeout=30)


# --- Settings threshold bounds ---
class TestSettingsThresholdBounds:
    def test_negative_threshold_rejected(self, client):
        r = client.put(f"{API}/settings", json={"overtime_alert_threshold": -5}, timeout=30)
        assert r.status_code == 422, f"expected 422, got {r.status_code}: {r.text[:200]}"

    def test_too_large_threshold_rejected(self, client):
        r = client.put(f"{API}/settings", json={"overtime_alert_threshold": 100000}, timeout=30)
        assert r.status_code == 422, f"expected 422, got {r.status_code}: {r.text[:200]}"

    def test_valid_threshold_persists_and_restores(self, client):
        r = client.put(f"{API}/settings", json={"overtime_alert_threshold": 15}, timeout=30)
        assert r.status_code == 200
        assert r.json()["overtime_alert_threshold"] == 15
        g = client.get(f"{API}/settings", timeout=30)
        assert g.status_code == 200
        assert g.json()["overtime_alert_threshold"] == 15
        client.put(f"{API}/settings", json={"overtime_alert_threshold": 30}, timeout=30)
        assert client.get(f"{API}/settings", timeout=30).json()["overtime_alert_threshold"] == 30


# --- validate-tech payload validation ---
class TestValidateTechValidation:
    def test_empty_payload_returns_422(self, client):
        r = client.post(f"{API}/overtime/validate-tech", json={}, timeout=30)
        assert r.status_code == 422, f"expected 422 (Pydantic model), got {r.status_code}: {r.text[:200]}"

    def test_invalid_month_returns_400(self, client):
        r = client.post(
            f"{API}/overtime/validate-tech",
            json={"technician_name": "TEST_OT9", "month": "9999-99"},
            timeout=30,
        )
        assert r.status_code == 400, f"expected 400, got {r.status_code}: {r.text[:200]}"
        assert "Mois invalide" in r.json().get("detail", "")


# --- grand_total correctness (server side) ---
class TestGrandTotalServer:
    TECH = "TEST_OT9_GT"

    def _cleanup(self, client):
        # NOTE: there is no DELETE /api/overtime/{id} endpoint — POST hours=0 deletes the entry.
        r = client.get(f"{API}/overtime?month=2026-08", timeout=30)
        for e in r.json().get("entries", []):
            if e.get("technician_name") == self.TECH:
                client.post(
                    f"{API}/overtime",
                    json={"technician_name": e["technician_name"], "date": e["date"], "hours": 0},
                    timeout=30,
                )

    def test_approved_plus_pending_sums(self, client):
        self._cleanup(client)
        try:
            r1 = client.post(f"{API}/overtime", json={"technician_name": self.TECH, "date": "2026-08-10", "hours": 7}, timeout=30)
            assert r1.status_code in (200, 201), r1.text[:200]
            eid = r1.json()["id"]
            rv = client.put(f"{API}/overtime/{eid}/validate", timeout=30)
            assert rv.status_code == 200
            r2 = client.post(f"{API}/overtime", json={"technician_name": self.TECH, "date": "2026-08-11", "hours": 2}, timeout=30)
            assert r2.status_code in (200, 201)

            g = client.get(f"{API}/overtime?month=2026-08", timeout=30)
            assert g.status_code == 200
            row = next(r for r in g.json()["rows"] if r["technician_name"] == self.TECH)
            assert row["approved_hours"] == 7
            assert row["pending_hours"] == 2
            assert row["total_hours"] == 9
        finally:
            self._cleanup(client)
