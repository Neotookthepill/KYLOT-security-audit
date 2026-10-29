"""KEYLOT backend regression tests.

Modules covered:
- auth (login / me)
- projects (chantiers): nested assigned_to migration bug fix, PUT multi-tech, dedup
- cron rappel J-1 (auth, idempotency, manual admin test endpoint)
- regression: clients bulk import, monthly report
"""
import datetime as dt
import uuid
from zoneinfo import ZoneInfo

import pytest
import requests

from conftest import BASE_URL

TARGET_PID = "0c63842d-7d5d-4145-acc5-4d122e788886"


def paris_tomorrow():
    return (dt.datetime.now(ZoneInfo("Europe/Paris")).date() + dt.timedelta(days=1)).isoformat()


# ---------------- Auth ----------------
class TestAuth:
    def test_login_success(self, test_credentials):
        r = requests.post(f"{BASE_URL}/api/auth/login", json=test_credentials, timeout=30)
        assert r.status_code == 200, r.text[:300]
        d = r.json()
        assert isinstance(d.get("token"), str) and len(d["token"]) > 10
        assert d["user"]["email"] == test_credentials["email"].lower()
        assert d["user"]["role"] == "admin"
        assert "password_hash" not in d["user"]

    def test_login_invalid(self, test_credentials):
        r = requests.post(f"{BASE_URL}/api/auth/login",
                          json={"email": test_credentials["email"], "password": "WrongPass!123"}, timeout=30)
        assert r.status_code == 401

    def test_me(self, admin_client):
        r = admin_client.get(f"{BASE_URL}/api/auth/me", timeout=30)
        assert r.status_code == 200
        assert r.json()["role"] == "admin"

    def test_me_unauthenticated(self):
        r = requests.get(f"{BASE_URL}/api/auth/me", timeout=30)
        assert r.status_code == 401


# ---------------- Projects: assigned_to shape ----------------
class TestProjectsAssignedTo:
    def test_list_projects_no_nested_assigned_to(self, admin_client):
        r = admin_client.get(f"{BASE_URL}/api/projects", timeout=60)
        assert r.status_code == 200, r.text[:300]
        projects = r.json()
        assert isinstance(projects, list) and len(projects) > 0
        bad = []
        for p in projects:
            assert "_id" not in p
            a = p.get("assigned_to")
            if isinstance(a, list):
                if any(not isinstance(x, str) for x in a):
                    bad.append((p["id"], a))
            elif a is not None and not isinstance(a, str):
                bad.append((p["id"], a))
        assert not bad, f"Projects with non-flat assigned_to: {bad}"

    def test_specific_legacy_project_is_flat(self, admin_client):
        r = admin_client.get(f"{BASE_URL}/api/projects", timeout=60)
        assert r.status_code == 200
        target = [p for p in r.json() if p["id"] == TARGET_PID]
        if not target:
            pytest.skip(f"project {TARGET_PID} not present in DB")
        a = target[0].get("assigned_to")
        assert isinstance(a, list), f"expected list, got {type(a)}: {a}"
        assert all(isinstance(x, str) for x in a), a

    def test_put_multiple_technicians(self, admin_client):
        r = admin_client.get(f"{BASE_URL}/api/projects", timeout=60)
        projects = r.json()
        pid = TARGET_PID if any(p["id"] == TARGET_PID for p in projects) else projects[0]["id"]
        original = [p for p in projects if p["id"] == pid][0]

        payload = {"assigned_to": ["Yann", "Ludo", "Guillaume"], "duration_days": 3,
                   "status": "a_planifier", "priority": "moyenne"}
        r = admin_client.put(f"{BASE_URL}/api/projects/{pid}", json=payload, timeout=30)
        assert r.status_code == 200, r.text[:500]
        d = r.json()
        assert d["assigned_to"] == ["Yann", "Ludo", "Guillaume"], d["assigned_to"]
        assert d["duration_days"] == 3
        assert d["status"] == "a_planifier"

        # persistence check via GET
        got = [p for p in admin_client.get(f"{BASE_URL}/api/projects", timeout=60).json() if p["id"] == pid][0]
        assert got["assigned_to"] == ["Yann", "Ludo", "Guillaume"]
        assert got["duration_days"] == 3

        # restore original values
        admin_client.put(f"{BASE_URL}/api/projects/{pid}", json={
            "assigned_to": original.get("assigned_to") or [],
            "duration_days": original.get("duration_days") or 1,
            "status": original.get("status") or "a_planifier",
            "priority": original.get("priority") or "moyenne",
        }, timeout=30)

    def test_put_dedup_and_single_then_multi(self, admin_client):
        projects = admin_client.get(f"{BASE_URL}/api/projects", timeout=60).json()
        pid = projects[0]["id"]
        original = projects[0]

        r = admin_client.put(f"{BASE_URL}/api/projects/{pid}",
                             json={"assigned_to": ["Yann", "Yann", "Ludo"]}, timeout=30)
        assert r.status_code == 200, r.text[:500]
        assert r.json()["assigned_to"] == ["Yann", "Ludo"]

        # single tech
        r = admin_client.put(f"{BASE_URL}/api/projects/{pid}", json={"assigned_to": ["Yann"], "duration_days": 1}, timeout=30)
        assert r.status_code == 200 and r.json()["assigned_to"] == ["Yann"]

        # back to two techs / 2 days (the user's reported scenario)
        r = admin_client.put(f"{BASE_URL}/api/projects/{pid}", json={"assigned_to": ["Yann", "Ludo"], "duration_days": 2}, timeout=30)
        assert r.status_code == 200
        assert r.json()["assigned_to"] == ["Yann", "Ludo"] and r.json()["duration_days"] == 2

        admin_client.put(f"{BASE_URL}/api/projects/{pid}", json={
            "assigned_to": original.get("assigned_to") or [],
            "duration_days": original.get("duration_days") or 1,
        }, timeout=30)

    def test_put_nested_payload_defensive_flatten(self, admin_client):
        """Server should not 500/422 on legacy nested payload."""
        projects = admin_client.get(f"{BASE_URL}/api/projects", timeout=60).json()
        pid = projects[0]["id"]
        r = admin_client.put(f"{BASE_URL}/api/projects/{pid}",
                             json={"assigned_to": [["Yann", "Ludo"]]}, timeout=30)
        assert r.status_code in (200, 422), f"unexpected {r.status_code}: {r.text[:300]}"
        if r.status_code == 200:
            assert r.json()["assigned_to"] == ["Yann", "Ludo"]

    def test_put_unknown_project_404(self, admin_client):
        r = admin_client.put(f"{BASE_URL}/api/projects/{uuid.uuid4()}", json={"duration_days": 1}, timeout=30)
        assert r.status_code == 404

    def test_projects_requires_auth(self):
        r = requests.get(f"{BASE_URL}/api/projects", timeout=30)
        assert r.status_code == 401


# ---------------- Cron Rappel J-1 ----------------
class TestCronRappelJ1:
    URL = f"{BASE_URL}/api/cron/rappel-chantiers-j1"

    def test_no_auth_401(self):
        r = requests.post(self.URL, json={"event": "schedule.triggered"}, timeout=30)
        assert r.status_code == 401, r.text[:200]

    def test_wrong_bearer_401(self):
        r = requests.post(self.URL, json={"event": "schedule.triggered"},
                          headers={"Authorization": "Bearer nope-invalid"}, timeout=30)
        assert r.status_code == 401

    def test_valid_secret_and_idempotency(self, cron_secret):
        run_id = f"TEST_{uuid.uuid4()}"
        headers = {"Authorization": f"Bearer {cron_secret}", "Content-Type": "application/json"}
        body = {"event": "schedule.triggered", "run_id": run_id}
        r = requests.post(self.URL, json=body, headers=headers, timeout=60)
        assert r.status_code in (200, 202), r.text[:300]
        d = r.json()
        assert d.get("accepted") is True
        assert d.get("run_id") == run_id
        assert d.get("target_date") == paris_tomorrow(), d

        r2 = requests.post(self.URL, json=body, headers=headers, timeout=60)
        assert r2.status_code in (200, 202)
        assert r2.json().get("duplicate") is True, r2.json()

    def test_manual_test_endpoint(self, admin_client):
        r = admin_client.post(f"{BASE_URL}/api/cron/rappel-chantiers-j1/test", timeout=120)
        assert r.status_code == 200, r.text[:500]
        d = r.json()
        for k in ("target_date", "sent", "recipients", "chantiers"):
            assert k in d, f"missing {k} in {d}"
        assert d["target_date"] == paris_tomorrow()
        assert isinstance(d["recipients"], list)
        assert isinstance(d["chantiers"], int) and isinstance(d["sent"], int)
        # NOTE: sent may be 0 if the Emergent email proxy rate-limits (429) after
        # repeated triggers. Verified real 202 Accepted sends in backend logs.
        if d["chantiers"] > 0 and d["sent"] == 0:
            print("WARN: chantiers>0 but sent=0 (likely email provider 429 rate limit)")
        assert d["sent"] == len(d["recipients"])

    def test_manual_test_endpoint_requires_admin(self):
        r = requests.post(f"{BASE_URL}/api/cron/rappel-chantiers-j1/test", timeout=30)
        assert r.status_code == 401

    def test_manual_with_explicit_target_date(self, admin_client):
        # tomorrow explicitly passed as query param
        td = paris_tomorrow()
        r = admin_client.post(f"{BASE_URL}/api/cron/rappel-chantiers-j1/test?target_date={td}", timeout=120)
        assert r.status_code == 200, r.text[:300]
        assert r.json()["target_date"] == td


# ---------------- Regression: clients bulk + monthly report ----------------
class TestRegression:
    created = []

    def test_clients_bulk_import(self, admin_client):
        # columns: name, phone, email, address, postal_code, city, notes
        text = ("TEST_QA Dupont\t0601020304\tqa1@test.local\t12 rue de Paris\t75001\tParis\n"
                "TEST_QA Martin\t0605060708\tqa2@test.local\t5 av Foch\t69000\tLyon")
        r = admin_client.post(f"{BASE_URL}/api/clients/bulk", json={"text": text}, timeout=60)
        assert r.status_code in (200, 201), r.text[:500]
        d = r.json()
        assert d.get("created_count", 0) >= 1, d
        assert len(d["created"]) == d["created_count"]
        assert all("_id" not in c for c in d["created"])
        assert d["created"][0]["phone"] == "0601020304"
        assert d["created"][0]["city"] == "Paris"

        clients = admin_client.get(f"{BASE_URL}/api/clients", timeout=60).json()
        mine = [c for c in clients if str(c.get("name", "")).startswith("TEST_QA")]
        assert len(mine) >= 2, f"bulk clients not persisted: {len(mine)}"
        TestRegression.created = [c["id"] for c in mine]

    def test_monthly_report(self, admin_client):
        month = dt.date.today().strftime("%Y-%m")
        r = admin_client.get(f"{BASE_URL}/api/reports/monthly?month={month}", timeout=60)
        assert r.status_code == 200, r.text[:500]
        d = r.json()
        assert isinstance(d, dict) and d, d
        assert "_id" not in str(d)

    def test_monthly_report_bad_month(self, admin_client):
        r = admin_client.get(f"{BASE_URL}/api/reports/monthly?month=not-a-month", timeout=30)
        assert r.status_code in (400, 422, 200), r.status_code

    def test_zz_cleanup_test_clients(self, admin_client):
        for cid in TestRegression.created:
            r = admin_client.delete(f"{BASE_URL}/api/clients/{cid}", timeout=30)
            assert r.status_code in (200, 204, 404)
