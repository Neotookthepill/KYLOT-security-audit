import os
import requests
from dotenv import dotenv_values
from _remote_test_guard import require_http_mutation_permission

BASE = (os.environ.get("REACT_APP_BACKEND_URL") or dotenv_values("/app/frontend/.env")["REACT_APP_BACKEND_URL"]).rstrip("/")
require_http_mutation_permission(BASE)
s = requests.Session()
r = s.post(f"{BASE}/api/auth/login", json={"email": "admin@example.invalid", "password": "CHANGE_ME_TEST_PASSWORD"}, timeout=30)
tok = r.json().get("access_token") or r.json().get("token")
s.headers.update({"Authorization": f"Bearer {tok}"})

users = s.get(f"{BASE}/api/users", timeout=30).json()
for u in users:
    if u.get("email") == "test-tech2@keylot.app" and u.get("role") == "sous_traitant":
        print("revert tech2", s.put(f"{BASE}/api/users/{u['id']}", json={"role": "technicien"}, timeout=30).status_code)
    if u.get("email") == "test-st-qa3@keylot.example.com":
        print("delete qa3 user", s.delete(f"{BASE}/api/users/{u['id']}", timeout=30).status_code)

team = s.get(f"{BASE}/api/team?type=sous_traitant", timeout=30).json()
print("team_members sous_traitant:", [(m["name"], m["id"]) for m in team])
for m in team:
    if m["name"].startswith("TEST_"):
        print("delete tm", m["name"], s.delete(f"{BASE}/api/team/{m['id']}", timeout=30).status_code)
