"""Iteration 13 — delta threshold edge cases: prev CA 0 / 500 (<1000) -> None, prev CA >=1000 -> number.

Uses period=prev (current window = previous month, previous window = month-2) and injects
temporary sales in the month-2 slot, then cleans them up.
"""
import os
import re
from datetime import date
from pathlib import Path

import pytest
import requests
from dotenv import dotenv_values

frontend_env = dotenv_values("/app/frontend/.env")
BASE_URL = (os.environ.get("REACT_APP_BACKEND_URL") or frontend_env.get("REACT_APP_BACKEND_URL")).rstrip("/")


def _month_minus(n):
    y, m = date.today().year, date.today().month
    m -= n
    while m <= 0:
        m += 12
        y -= 1
    return f"{y}-{m:02d}"


@pytest.fixture(scope="module")
def client():
    content = Path("/app/memory/test_credentials.md").read_text(encoding="utf-8")
    _m = re.search(r'(?is)^##\s*(?:Default company admin|Admin\b).*?(?=^##\s|\Z)', content, re.M)
    if _m:
        content = _m.group(0)  # skip the super-admin block (403 on tenant endpoints)
    email = re.search(r"(?im)^\s*-\s*Email:\s*`?([^`\s]+)", content).group(1)
    password = re.search(r"(?im)^\s*-\s*Password:\s*`?([^`\s]+)", content).group(1)
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/login", json={"email": email, "password": password}, timeout=30)
    if r.status_code != 200:
        pytest.fail(f"login failed {r.status_code}: {r.text[:300]}")
    token = r.json().get("token") or r.json().get("access_token")
    assert token
    s.headers.update({"Authorization": f"Bearer {token}"})
    return s


def _exec(client, period="prev"):
    r = client.get(f"{BASE_URL}/api/dashboard/executive?period={period}", timeout=60)
    assert r.status_code == 200, r.text[:300]
    return r.json()


def _create_sale(client, amount, sale_date):
    payload = {
        "client": {"name": "TEST_QA_DeltaClient", "phone": "0600000000"},
        "service": "TEST_QA",
        "amount": amount,
        "sale_date": sale_date,
        "commercial": "TEST_QA_Com",
        "status": "commercial_cheque",
    }
    r = client.post(f"{BASE_URL}/api/sales", json=payload, timeout=30)
    assert r.status_code in (200, 201), r.text[:300]
    return r.json()["id"]


def test_prev_base_thresholds(client):
    created = []
    prev_prev_slot = f"{_month_minus(2)}-10"
    try:
        base = _exec(client)
        print("baseline prev-period:", base["ca"], base["sales"])
        # month-2 has no CA in seed data -> delta must be None
        assert base["ca"]["delta_pct"] is None, "expected None when previous base CA is 0"

        # Inject 500€ (below the 1000€ threshold) -> still None
        created.append(_create_sale(client, 500, prev_prev_slot))
        d = _exec(client)
        print("with prev CA=500:", d["ca"], d["sales"])
        assert d["ca"]["delta_pct"] is None, f"expected None for prev CA=500, got {d['ca']['delta_pct']}"
        assert d["sales"]["delta_pct"] is None, f"expected None for prev count=1, got {d['sales']['delta_pct']}"

        # Bring prev base above 1000€ (500+900=1400) and count to 3 -> numbers expected
        created.append(_create_sale(client, 900, prev_prev_slot))
        created.append(_create_sale(client, 100, prev_prev_slot))
        d = _exec(client)
        print("with prev CA=1500 / count=3:", d["ca"], d["sales"])
        assert isinstance(d["ca"]["delta_pct"], (int, float)), "expected numeric delta once prev CA >= 1000"
        assert isinstance(d["sales"]["delta_pct"], (int, float)), "expected numeric delta once prev count >= 3"
    finally:
        for sid in created:
            r = client.delete(f"{BASE_URL}/api/sales/{sid}", timeout=30)
            assert r.status_code in (200, 204), r.text[:200]
        after = _exec(client)
        assert after["ca"]["delta_pct"] is None, "cleanup incomplete: prev CA still non-zero"
