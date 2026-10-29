"""Seed data for the iteration-16 UI session: enable new_sales, create a sale as the
commercial so the admin has one unread notification + audit entries."""
import requests
from dotenv import dotenv_values
from _remote_test_guard import require_http_mutation_permission

BASE = dotenv_values("/app/frontend/.env")["REACT_APP_BACKEND_URL"].rstrip("/")
require_http_mutation_permission(BASE)
ADMIN = {"email": "admin@example.invalid", "password": "CHANGE_ME_TEST_PASSWORD"}
COM = {"email": "com1@keylot.example.com", "password": "Com@2026"}
CATS = ["new_sales", "objectives", "planning", "overtime", "project_alerts"]


def h(tok):
    return {"Authorization": f"Bearer {tok}", "Content-Type": "application/json"}


at = requests.post(f"{BASE}/api/auth/login", json=ADMIN, timeout=30).json()["token"]
prefs = {k: False for k in CATS}
prefs["new_sales"] = True
print("settings:", requests.put(f"{BASE}/api/settings", json={"notifications": prefs}, headers=h(at), timeout=30).json()["notifications"])

ct = requests.post(f"{BASE}/api/auth/login", json=COM, timeout=30).json()["token"]
cid = requests.get(f"{BASE}/api/clients", headers=h(at), timeout=30).json()[0]["id"]
r = requests.post(f"{BASE}/api/sales", json={
    "client_id": cid, "service": "TEST_UI Notif Sale", "amount": 7777,
    "sale_date": "2026-07-05", "commercial": "TEST_Com1",
}, headers=h(ct), timeout=30)
print("sale:", r.status_code, r.json().get("id"))
n = requests.get(f"{BASE}/api/notifications", headers=h(at), timeout=30).json()
print("admin unread:", n["unread"])
print("audit entries:", len(requests.get(f"{BASE}/api/audit", headers=h(at), timeout=30).json()))
