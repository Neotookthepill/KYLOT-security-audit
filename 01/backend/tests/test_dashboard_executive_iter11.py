# Tests for the executive dashboard endpoint /api/dashboard/executive (iteration 11)
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
    # Scope to the company-admin section (the file starts with the super-admin account,
    # which is now rejected on tenant endpoints with 403).
    section = re.search(r'(?is)^##\s*(?:Default company admin|Admin\b).*?(?=^##\s|\Z)', content, re.M)
    if section:
        content = section.group(0)
    email = re.search(r'(?im)^\s*[-*]?\s*Email:\s*`?([^`\s]+)', content)
    pwd = re.search(r'(?im)^\s*[-*]?\s*Password:\s*`?([^`\s]+)', content)
    if not email or not pwd:
        pytest.skip("credentials not found")
    return {"email": email.group(1), "password": pwd.group(1)}


@pytest.fixture(scope="module")
def client(creds):
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    r = s.post(f"{BASE_URL}/api/auth/login", json=creds, timeout=30)
    if r.status_code != 200 or not r.json().get("token"):
        pytest.fail(f"admin login failed: {r.status_code} {r.text[:300]}")
    s.headers.update({"Authorization": f"Bearer {r.json()['token']}"})
    return s


@pytest.mark.parametrize("period", ["month", "prev", "year"])
def test_executive_returns_expected_shape(client, period):
    r = client.get(f"{BASE_URL}/api/dashboard/executive?period={period}", timeout=30)
    assert r.status_code == 200, f"expected 200, got {r.status_code}: {r.text[:300]}"
    d = r.json()
    assert d["period"] == period
    assert set(["start", "end"]).issubset(d["range"].keys())
    for k in ("total", "objectif", "progress"):
        assert k in d["ca"]
    assert "count" in d["sales"]
    assert isinstance(d["clients_count"], int)
    for k in ("to_schedule", "in_progress", "completed"):
        assert k in d["projects"]
    assert isinstance(d["ranking"], list)
    cas = [x["ca"] for x in d["ranking"]]
    assert cas == sorted(cas, reverse=True)
    for row in d["ranking"]:
        for k in ("commercial", "ca", "count", "objectif", "progress"):
            assert k in row
    for k in ("total", "to_validate_count", "to_validate_amount"):
        assert k in d["commissions"]
    for k in ("pending_hours", "pending_count"):
        assert k in d["overtime"]
    for a in d["alerts"]:
        assert set(["key", "label", "count", "href"]).issubset(a.keys())
    assert isinstance(d["recent_sales"], list)

    # No raw Mongo ObjectId keys anywhere in the payload (substring check would false-positive
    # on legitimate fields such as "client_id"/"company_id").
    def _no_mongo_id(node):
        if isinstance(node, dict):
            assert "_id" not in node, f"_id leaked in {list(node.keys())}"
            for v in node.values():
                _no_mongo_id(v)
        elif isinstance(node, list):
            for v in node:
                _no_mongo_id(v)

    _no_mongo_id(d)


def test_executive_ca_matches_sales_aggregation(client):
    r = client.get(f"{BASE_URL}/api/dashboard/executive?period=year", timeout=30)
    assert r.status_code == 200, f"{r.status_code}: {r.text[:200]}"
    exec_ca = r.json()["ca"]["total"]
    sales = client.get(f"{BASE_URL}/api/sales", timeout=30).json()
    year = r.json()["range"]["start"][:4]
    total = sum(
        float(s.get("amount") or 0)
        for s in sales
        if str(s.get("sale_date", "")).startswith(year)
        and str(s.get("status", "")).lower() not in ("annule", "annulé", "litige")
    )
    assert abs(exec_ca - total) < 1, f"executive CA {exec_ca} != sales aggregation {total}"


def test_executive_requires_auth():
    r = requests.get(f"{BASE_URL}/api/dashboard/executive?period=month", timeout=30)
    assert r.status_code in (401, 403), f"unauthenticated call returned {r.status_code}"


# Regression: legacy stats endpoint kept for backward compat
def test_legacy_dashboard_stats_still_ok(client):
    r = client.get(f"{BASE_URL}/api/dashboard/stats", timeout=30)
    assert r.status_code == 200
    d = r.json()
    for k in ("sales_count", "ca_total", "clients_count", "to_schedule", "in_progress"):
        assert k in d
