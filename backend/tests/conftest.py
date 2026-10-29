import os
import re
from pathlib import Path

import pytest
import requests
from dotenv import dotenv_values
from backend.tests._remote_test_guard import require_http_mutation_permission

frontend_env = dotenv_values("/app/frontend/.env")
_base = os.environ.get("REACT_APP_BACKEND_URL") or frontend_env.get("REACT_APP_BACKEND_URL")
if not _base:
    raise RuntimeError("REACT_APP_BACKEND_URL missing")
BASE_URL = _base.rstrip("/")
require_http_mutation_permission(BASE_URL)

backend_env = dotenv_values("/app/backend/.env")


@pytest.fixture(scope="session")
def base_url():
    return BASE_URL


@pytest.fixture(scope="session")
def cron_secret():
    s = backend_env.get("WEBHOOK_CRON_SECRET")
    if not s:
        pytest.fail("WEBHOOK_CRON_SECRET missing from /app/backend/.env")
    return s


@pytest.fixture(scope="session")
def test_credentials():
    p = Path("/app/memory/test_credentials.md")
    if not p.exists():
        pytest.skip("Missing /app/memory/test_credentials.md")
    content = p.read_text(encoding="utf-8")
    # The file now documents several accounts (super-admin first). Scope the parsing to the
    # "## Admin" section so these regression tests keep using the default-company admin.
    admin_section = re.search(
        r'(?is)^##\s*(?:Default company admin|Admin\b).*?(?=^##\s|\Z)', content, re.M
    )
    if admin_section:
        content = admin_section.group(0)
    email = re.search(r'(?im)^\s*(?:[-*]\s*)?(?:\*\*)?Email(?:\*\*)?\s*:\s*`?([^`\s]+)', content)
    pwd = re.search(r'(?im)^\s*(?:[-*]\s*)?(?:\*\*)?Password(?:\*\*)?\s*:\s*`?([^`\s]+)', content)
    if not email or not pwd:
        pytest.skip("No credentials found in test_credentials.md")
    return {"email": email.group(1), "password": pwd.group(1)}


@pytest.fixture(scope="session")
def api_client():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


@pytest.fixture(scope="session")
def admin_token(test_credentials):
    r = requests.post(f"{BASE_URL}/api/auth/login", json=test_credentials, timeout=30)
    if r.status_code != 200:
        pytest.fail(f"Admin login failed {r.status_code}: {r.text[:300]}")
    tok = r.json().get("token")
    if not tok:
        pytest.fail("No token in login response")
    return tok


@pytest.fixture(scope="session")
def admin_client(admin_token):
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json", "Authorization": f"Bearer {admin_token}"})
    return s
