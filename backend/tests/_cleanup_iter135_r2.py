"""Cleanup des team_members de test iter135 (préfixe TEST_QA_ST / TEST_ST)."""
import os
import requests
from dotenv import dotenv_values

BASE_URL = (os.environ.get("REACT_APP_BACKEND_URL") or dotenv_values("/app/frontend/.env")["REACT_APP_BACKEND_URL"]).rstrip("/")
s = requests.Session()
r = s.post(f"{BASE_URL}/api/auth/login", json={"email": "admin@example.invalid", "password": "CHANGE_ME_TEST_PASSWORD"}, timeout=30)
r.raise_for_status()
s.headers.update({"Authorization": f"Bearer {r.json().get('access_token') or r.json().get('token')}"})
members = s.get(f"{BASE_URL}/api/team?type=sous_traitant", timeout=30).json()
for m in members:
    if (m.get("name") or "").startswith(("TEST_QA_ST", "TEST_ST")):
        d = s.delete(f"{BASE_URL}/api/team/{m['id']}", timeout=30)
        print("deleted", m["name"], d.status_code)
print("remaining:", [m.get("name") for m in s.get(f"{BASE_URL}/api/team?type=sous_traitant", timeout=30).json()])
