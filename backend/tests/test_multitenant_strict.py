"""
Strict multi-tenant isolation test suite (company_A vs company_B).
Verifies that no user of A can read/modify/delete/create data of B via API,
even by tampering with URLs, IDs, body payloads.

Run: pytest /app/backend/tests/test_multitenant_strict.py -v -n 0
"""
import os
import uuid
import pytest
import httpx

API = (os.environ.get("REACT_APP_BACKEND_URL") or "http://127.0.0.1:8000").rstrip("/") + "/api"
SUPER = {"email": "super@keylot.app", "password": "Super@2026"}


def _login(client, email, password):
    r = client.post(f"{API}/auth/login", json={"email": email, "password": password})
    r.raise_for_status()
    return r.json()["token"]


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture(scope="module")
def ctx():
    """Create company_A and company_B with users, clients, sales, projects, prospects."""
    with httpx.Client(timeout=30) as c:
        super_token = _login(c, SUPER["email"], SUPER["password"])
        s = _auth(super_token)

        # Unique suffix so tests can be replayed
        sfx = uuid.uuid4().hex[:6]
        payload_a = {"name": f"Company_A_{sfx}", "admin_email": f"admin_a_{sfx}@keylot.example.com", "admin_password": "PassA@2026", "admin_name": "Admin A"}
        payload_b = {"name": f"Company_B_{sfx}", "admin_email": f"admin_b_{sfx}@keylot.example.com", "admin_password": "PassB@2026", "admin_name": "Admin B"}
        ra = c.post(f"{API}/superadmin/companies", headers=s, json=payload_a); ra.raise_for_status()
        rb = c.post(f"{API}/superadmin/companies", headers=s, json=payload_b); rb.raise_for_status()
        A = ra.json()["company"]; B = rb.json()["company"]

        tA = _login(c, payload_a["admin_email"], payload_a["admin_password"])
        tB = _login(c, payload_b["admin_email"], payload_b["admin_password"])

        # Seed each company with 1 client + 1 sale + 1 project + 1 prospect
        def seed(token, label):
            h = _auth(token)
            client = c.post(f"{API}/clients", headers=h, json={"name": f"Client {label}", "phone": "0600000000", "city": "Lyon"}).json()
            sale = c.post(f"{API}/sales", headers=h, json={"client_id": client["id"], "service": f"Test service {label}", "amount": 1000, "commission_rate": 0.1, "sale_date": "2026-08-01"}).json()
            projects = c.get(f"{API}/projects", headers=h).json()
            project = projects[0] if projects else {}
            prospect = c.post(f"{API}/prospects", headers=h, json={"name": f"Lead {label}", "phone": "0611111111", "source": "scan_maison"}).json()
            return {"client": client, "sale": sale, "project": project, "prospect": prospect}

        A_data = seed(tA, "A")
        B_data = seed(tB, "B")

        # Create a commercial user in each company
        userA = c.post(f"{API}/users", headers=_auth(tA), json={"email": f"com_a_{sfx}@keylot.example.com", "password": "ComA@2026", "name": "Com A", "role": "commercial"}).json()
        userB = c.post(f"{API}/users", headers=_auth(tB), json={"email": f"com_b_{sfx}@keylot.example.com", "password": "ComB@2026", "name": "Com B", "role": "commercial"}).json()

        yield {
            "A": {"company": A, "admin_token": tA, "data": A_data, "user": userA, "admin_email": payload_a["admin_email"]},
            "B": {"company": B, "admin_token": tB, "data": B_data, "user": userB, "admin_email": payload_b["admin_email"]},
        }

        # Cleanup: delete both companies (cascades to all data)
        c.delete(f"{API}/superadmin/companies/{A['id']}", headers=s)
        c.delete(f"{API}/superadmin/companies/{B['id']}", headers=s)


@pytest.fixture
def http():
    with httpx.Client(timeout=30) as c:
        yield c


class TestMultiTenantIsolation:
    """A user of Company A must never access any Company B data."""

    def test_A_lists_only_A_clients(self, http, ctx):
        r = http.get(f"{API}/clients", headers=_auth(ctx["A"]["admin_token"]))
        r.raise_for_status()
        ids = {c["id"] for c in r.json()}
        assert ctx["A"]["data"]["client"]["id"] in ids
        assert ctx["B"]["data"]["client"]["id"] not in ids

    def test_A_lists_only_A_sales(self, http, ctx):
        r = http.get(f"{API}/sales", headers=_auth(ctx["A"]["admin_token"]))
        r.raise_for_status()
        ids = {s["id"] for s in r.json()}
        assert ctx["A"]["data"]["sale"]["id"] in ids
        assert ctx["B"]["data"]["sale"]["id"] not in ids

    def test_A_lists_only_A_projects(self, http, ctx):
        r = http.get(f"{API}/projects", headers=_auth(ctx["A"]["admin_token"]))
        r.raise_for_status()
        ids = {p["id"] for p in r.json()}
        assert ctx["B"]["data"]["project"].get("id") not in ids

    def test_A_lists_only_A_prospects(self, http, ctx):
        r = http.get(f"{API}/prospects", headers=_auth(ctx["A"]["admin_token"]))
        r.raise_for_status()
        ids = {p["id"] for p in r.json()}
        assert ctx["A"]["data"]["prospect"]["id"] in ids
        assert ctx["B"]["data"]["prospect"]["id"] not in ids

    def test_A_lists_only_A_users(self, http, ctx):
        r = http.get(f"{API}/users", headers=_auth(ctx["A"]["admin_token"]))
        r.raise_for_status()
        emails = {u["email"] for u in r.json()}
        assert ctx["A"]["admin_email"] in emails
        assert ctx["B"]["admin_email"] not in emails

    def test_A_cannot_get_B_sale_by_id_via_delete(self, http, ctx):
        r = http.delete(f"{API}/sales/{ctx['B']['data']['sale']['id']}", headers=_auth(ctx["A"]["admin_token"]))
        assert r.status_code == 404

    def test_A_cannot_update_B_sale(self, http, ctx):
        r = http.put(f"{API}/sales/{ctx['B']['data']['sale']['id']}", headers=_auth(ctx["A"]["admin_token"]), json={"status": "annule"})
        assert r.status_code == 404

    def test_A_cannot_delete_B_client(self, http, ctx):
        r = http.delete(f"{API}/clients/{ctx['B']['data']['client']['id']}", headers=_auth(ctx["A"]["admin_token"]))
        assert r.status_code == 404

    def test_A_cannot_update_B_client(self, http, ctx):
        r = http.put(f"{API}/clients/{ctx['B']['data']['client']['id']}", headers=_auth(ctx["A"]["admin_token"]), json={"name": "HACKED"})
        assert r.status_code == 404

    def test_A_cannot_update_B_project(self, http, ctx):
        pid = ctx["B"]["data"]["project"].get("id")
        if not pid: pytest.skip("no B project")
        r = http.put(f"{API}/projects/{pid}", headers=_auth(ctx["A"]["admin_token"]), json={"status": "termine"})
        assert r.status_code == 404

    def test_A_cannot_delete_B_project(self, http, ctx):
        pid = ctx["B"]["data"]["project"].get("id")
        if not pid: pytest.skip("no B project")
        r = http.delete(f"{API}/projects/{pid}", headers=_auth(ctx["A"]["admin_token"]))
        assert r.status_code == 404

    def test_A_cannot_delete_B_user(self, http, ctx):
        r = http.delete(f"{API}/users/{ctx['B']['user']['id']}", headers=_auth(ctx["A"]["admin_token"]))
        assert r.status_code == 404

    def test_A_cannot_update_B_user(self, http, ctx):
        r = http.put(f"{API}/users/{ctx['B']['user']['id']}", headers=_auth(ctx["A"]["admin_token"]), json={"name": "HACKED"})
        assert r.status_code == 404

    def test_A_cannot_update_B_user_permissions(self, http, ctx):
        r = http.put(f"{API}/users/{ctx['B']['user']['id']}/permissions", headers=_auth(ctx["A"]["admin_token"]), json={"permissions": {}})
        assert r.status_code == 404

    def test_A_cannot_delete_B_prospect(self, http, ctx):
        r = http.delete(f"{API}/prospects/{ctx['B']['data']['prospect']['id']}", headers=_auth(ctx["A"]["admin_token"]))
        assert r.status_code == 404

    def test_A_cannot_update_B_prospect(self, http, ctx):
        r = http.put(f"{API}/prospects/{ctx['B']['data']['prospect']['id']}", headers=_auth(ctx["A"]["admin_token"]), json={"name": "HACKED"})
        assert r.status_code == 404

    def test_A_cannot_convert_B_prospect(self, http, ctx):
        r = http.post(f"{API}/prospects/{ctx['B']['data']['prospect']['id']}/convert", headers=_auth(ctx["A"]["admin_token"]))
        assert r.status_code == 404

    def test_body_injection_company_id_ignored(self, http, ctx):
        """Attempt to inject a company_id via body — backend must ignore it and use JWT scope."""
        r = http.post(f"{API}/clients", headers=_auth(ctx["A"]["admin_token"]),
                      json={"name": "TAMPERED", "company_id": ctx["B"]["company"]["id"]})
        r.raise_for_status()
        created = r.json()
        # The created client MUST belong to A, never to B
        r2 = http.get(f"{API}/clients", headers=_auth(ctx["B"]["admin_token"]))
        b_ids = {c["id"] for c in r2.json()}
        assert created["id"] not in b_ids, "Client was leaked into company B"
        # Cleanup
        http.delete(f"{API}/clients/{created['id']}", headers=_auth(ctx["A"]["admin_token"]))

    def test_A_settings_isolation(self, http, ctx):
        """Changing A's settings must not affect B's settings."""
        # Set A app_name
        http.put(f"{API}/settings", headers=_auth(ctx["A"]["admin_token"]), json={"app_name": "APP_A"}).raise_for_status()
        http.put(f"{API}/settings", headers=_auth(ctx["B"]["admin_token"]), json={"app_name": "APP_B"}).raise_for_status()
        ra = http.get(f"{API}/settings", headers=_auth(ctx["A"]["admin_token"])).json()
        rb = http.get(f"{API}/settings", headers=_auth(ctx["B"]["admin_token"])).json()
        assert ra["app_name"] == "APP_A"
        assert rb["app_name"] == "APP_B"

    def test_commercial_of_A_cannot_see_B_data(self, http, ctx):
        """A commercial of company A (not admin) must also not see any B data."""
        # login as com A
        tok = _login(http, ctx["A"]["user"]["email"], "ComA@2026")
        h = _auth(tok)
        r_sales = http.get(f"{API}/sales", headers=h); r_sales.raise_for_status()
        r_clients = http.get(f"{API}/clients", headers=h); r_clients.raise_for_status()
        # Commercial has 'own' scope so both should be empty (they don't own anything yet)
        sale_ids = {s["id"] for s in r_sales.json()}
        client_ids = {c["id"] for c in r_clients.json()}
        assert ctx["B"]["data"]["sale"]["id"] not in sale_ids
        assert ctx["B"]["data"]["client"]["id"] not in client_ids

    def test_prospect_has_source_field(self, http, ctx):
        p = ctx["A"]["data"]["prospect"]
        assert p.get("source") == "scan_maison"
        assert p.get("status") == "nouveau"

    def test_prospect_source_validation(self, http, ctx):
        r = http.post(f"{API}/prospects", headers=_auth(ctx["A"]["admin_token"]),
                      json={"name": "Bad", "source": "not_a_source"})
        assert r.status_code == 400
        assert "Source invalide" in r.text

    def test_A_audit_does_not_see_B_actions(self, http, ctx):
        r = http.get(f"{API}/audit", headers=_auth(ctx["A"]["admin_token"]))
        r.raise_for_status()
        items = r.json()
        # No audit entry should reference a B resource_id
        b_ids = {ctx["B"]["data"]["client"]["id"], ctx["B"]["data"]["sale"]["id"],
                 ctx["B"]["data"]["prospect"]["id"], ctx["B"]["user"]["id"]}
        assert not any(it.get("resource_id") in b_ids for it in items)
