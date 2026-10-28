"""Iteration 12 — dashboard delta cap (CA<1000 -> None, sales count<3 -> None) + alerts hrefs."""
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


@pytest.fixture(scope="module")
def creds():
    content = Path("/app/memory/test_credentials.md").read_text(encoding="utf-8")
    _m = re.search(r'(?is)^##\s*(?:Default company admin|Admin\b).*?(?=^##\s|\Z)', content, re.M)
    if _m:
        content = _m.group(0)  # skip the super-admin block (403 on tenant endpoints)
    email = re.search(r"(?im)^\s*-\s*Email:\s*`?([^`\s]+)", content).group(1)
    password = re.search(r"(?im)^\s*-\s*Password:\s*`?([^`\s]+)", content).group(1)
    return {"email": email, "password": password}


@pytest.fixture(scope="module")
def client(creds):
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/login", json=creds, timeout=30)
    if r.status_code != 200:
        pytest.fail(f"login failed {r.status_code}: {r.text[:300]}")
    token = r.json().get("access_token") or r.json().get("token")
    assert token, r.json()
    s.headers.update({"Authorization": f"Bearer {token}"})
    return s


@pytest.mark.parametrize("period", ["month", "prev", "year"])
def test_executive_delta_caps(client, period):
    r = client.get(f"{BASE_URL}/api/dashboard/executive?period={period}", timeout=60)
    assert r.status_code == 200, r.text[:300]
    d = r.json()
    ca_delta = d["ca"]["delta_pct"]
    sales_delta = d["sales"]["delta_pct"]
    print(f"period={period} ca={d['ca']['total']} ca_delta={ca_delta} count={d['sales']['count']} sales_delta={sales_delta}")
    # Deltas must not be absurd (implies tiny previous base was not capped)
    if ca_delta is not None:
        assert abs(ca_delta) <= 300, f"absurd ca delta_pct {ca_delta} for period {period}"
    if sales_delta is not None:
        assert abs(sales_delta) <= 300, f"absurd sales delta_pct {sales_delta} for period {period}"


def test_alerts_hrefs(client):
    r = client.get(f"{BASE_URL}/api/dashboard/executive?period=month", timeout=60)
    assert r.status_code == 200
    expected = {"to_schedule": "/chantiers", "overtime": "/heures-sup", "commissions": "/commissions"}
    alerts = r.json().get("alerts", [])
    print("alerts:", alerts)
    for a in alerts:
        assert a["key"] in expected, f"unknown alert key {a['key']}"
        assert a["href"] == expected[a["key"]]
        assert a["count"] > 0


def test_overtime_zero_hours_deletes(client):
    """Reject button posts hours=0 → entry removed."""
    tech = "TEST_QA_Tech"
    d = "2026-07-15"
    r = client.post(f"{BASE_URL}/api/overtime", json={"technician_name": tech, "date": d, "hours": 3}, timeout=30)
    assert r.status_code in (200, 201), r.text[:300]
    month = d[:7]
    lst = client.get(f"{BASE_URL}/api/overtime?month={month}", timeout=30).json()
    assert any(e["technician_name"] == tech and e["date"] == d for e in lst["entries"])
    r = client.post(f"{BASE_URL}/api/overtime", json={"technician_name": tech, "date": d, "hours": 0}, timeout=30)
    assert r.status_code in (200, 201), r.text[:300]
    lst = client.get(f"{BASE_URL}/api/overtime?month={month}", timeout=30).json()
    assert not any(e["technician_name"] == tech and e["date"] == d for e in lst["entries"]), "hours=0 did not delete entry"
