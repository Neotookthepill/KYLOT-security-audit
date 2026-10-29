"""Seed data for iteration 17 UI tests: 2 technicien users, a project co-assigned, an absence today."""
import os
from datetime import date, timedelta
import requests
from dotenv import dotenv_values
from _remote_test_guard import require_http_mutation_permission

fe = dotenv_values("/app/frontend/.env")
BASE = (os.environ.get("REACT_APP_BACKEND_URL") or fe["REACT_APP_BACKEND_URL"]).rstrip("/") + "/api"
require_http_mutation_permission(BASE)
ADMIN = ("admin@example.invalid", "CHANGE_ME_TEST_PASSWORD")
TECHS = [
    ("test-tech@keylot.app", "Tech@2026", "TEST_Tech_QA"),
    ("test-tech2@keylot.app", "Tech@2026", "TEST_Tech2_QA"),
]
TODAY = date.today().isoformat()
TO = (date.today() + timedelta(days=1)).isoformat()


def client(email, pwd):
    r = requests.post(f"{BASE}/auth/login", json={"email": email, "password": pwd}, timeout=30)
    r.raise_for_status()
    s = requests.Session()
    s.headers.update({"Authorization": f"Bearer {r.json()['token']}"})
    return s


a = client(*ADMIN)
for email, pwd, name in TECHS:
    lr = requests.post(f"{BASE}/auth/login", json={"email": email, "password": pwd}, timeout=30)
    if lr.status_code != 200:
        cr = a.post(f"{BASE}/users", json={"email": email, "password": pwd, "name": name, "role": "technicien"})
        print("create user", email, cr.status_code, cr.text[:200])
    else:
        print("user exists", email)

projects = a.get(f"{BASE}/projects").json()
print("projects:", len(projects))
pid = projects[0]["id"]
r = a.put(f"{BASE}/projects/{pid}", json={
    "assigned_to": [TECHS[0][2], TECHS[1][2]],
    "scheduled_date": TODAY,
    "status": "planifie",
})
print("project update", r.status_code, r.json().get("assigned_to"), r.json().get("scheduled_date"))
print("PROJECT_ID", pid, "CLIENT", r.json().get("client_id"))

ab = a.post(f"{BASE}/absences", json={
    "person_name": TECHS[0][2], "person_type": "technicien",
    "date_from": TODAY, "date_to": TO, "reason": "TEST_UI_Conge"})
print("absence", ab.status_code, ab.text[:250])
print("ABSENCE_ID", ab.json().get("id"))
print("SETTINGS rates", a.get(f"{BASE}/settings").json().get("commission_rates"))
