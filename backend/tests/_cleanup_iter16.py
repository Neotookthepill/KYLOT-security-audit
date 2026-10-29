"""Cleanup after the iteration-16 test session: remove TEST_ sales created during the
session, purge notifications, reset notification prefs to all-OFF (product default),
restore app_name and drop the orphan sale left by a previous iteration."""
import requests
from dotenv import dotenv_values
from _remote_test_guard import require_http_mutation_permission

BASE = dotenv_values("/app/frontend/.env")["REACT_APP_BACKEND_URL"].rstrip("/")
require_http_mutation_permission(BASE)
ADMIN = {"email": "admin@example.invalid", "password": "CHANGE_ME_TEST_PASSWORD"}
CATS = ["new_sales", "objectives", "planning", "overtime", "project_alerts"]
PREFIXES = ("TEST_UI Notif", "TEST_Notif", "TEST_Isolation Notif", "TEST_Audit Delete", "TEST Thomas sale")

tok = requests.post(f"{BASE}/api/auth/login", json=ADMIN, timeout=30).json()["token"]
H = {"Authorization": f"Bearer {tok}", "Content-Type": "application/json"}

sales = requests.get(f"{BASE}/api/sales", headers=H, timeout=30).json()
removed = 0
for s in sales:
    if any((s.get("service") or "").startswith(p) for p in PREFIXES):
        r = requests.delete(f"{BASE}/api/sales/{s['id']}", headers=H, timeout=30)
        removed += r.status_code == 200
print("sales removed:", removed)

for it in requests.get(f"{BASE}/api/notifications", headers=H, timeout=30).json()["items"]:
    requests.delete(f"{BASE}/api/notifications/{it['id']}", headers=H, timeout=30)

r = requests.put(f"{BASE}/api/settings", headers=H, timeout=30, json={
    "notifications": {k: False for k in CATS}, "app_name": "KEYLOT",
})
print("settings reset:", r.status_code, r.json()["notifications"], r.json()["app_name"])
print("remaining notifications:", requests.get(f"{BASE}/api/notifications", headers=H, timeout=30).json()["unread"])
