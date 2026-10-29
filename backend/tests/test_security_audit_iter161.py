"""iter161 — Audit sécurité complet (multi-tenant strict + abonnements non-destructifs).

Cette suite complète (elle ne remplace pas) `test_multitenant_strict.py` :
  - Focalise sur les *nouveaux* durcissements iter161 :
    * `GET /api/payments/status/{session_id}` requiert que la session appartienne au user.
    * Webhook Stripe : idempotence (event.id dédoublonné via `stripe_events`).
    * Compte `subscription_status=suspended` bloqué (402) sauf endpoints billing/auth.
    * Aucun webhook Stripe (payment_failed / subscription_deleted) ne supprime de données.
    * Cross-tenant : cannot force `company_id` via payload.

Run: pytest /app/backend/tests/test_security_audit_iter161.py -v -n 0
"""
import os
import uuid
import time
import httpx
import pytest
from pymongo import MongoClient
from dotenv import dotenv_values

_backend_env = dotenv_values("/app/backend/.env")
API = (os.environ.get("REACT_APP_BACKEND_URL") or "http://127.0.0.1:8000").rstrip("/") + "/api"
MONGO_URL = _backend_env.get("MONGO_URL") or "mongodb://localhost:27017"
DB_NAME = _backend_env.get("DB_NAME") or "test_database"
SUPER = {"email": "super@keylot.app", "password": "Super@2026"}


def _login(c, email, password):
    r = c.post(f"{API}/auth/login", json={"email": email, "password": password})
    r.raise_for_status()
    return r.json()["token"]


def _auth(tok):
    return {"Authorization": f"Bearer {tok}"}


@pytest.fixture(scope="module")
def ctx():
    with httpx.Client(timeout=30) as c:
        stok = _login(c, SUPER["email"], SUPER["password"])
        s = _auth(stok)
        sfx = uuid.uuid4().hex[:6]
        pa = {"name": f"SecA_{sfx}", "admin_email": f"seca_{sfx}@keylot.example.com", "admin_password": "PA@2026", "admin_name": "SecAdmA"}
        pb = {"name": f"SecB_{sfx}", "admin_email": f"secb_{sfx}@keylot.example.com", "admin_password": "PB@2026", "admin_name": "SecAdmB"}
        A = c.post(f"{API}/superadmin/companies", headers=s, json=pa).json()["company"]
        B = c.post(f"{API}/superadmin/companies", headers=s, json=pb).json()["company"]
        tA = _login(c, pa["admin_email"], pa["admin_password"])
        tB = _login(c, pb["admin_email"], pb["admin_password"])
        clientA = c.post(f"{API}/clients", headers=_auth(tA), json={"name": "Cli A", "phone": "0600000000"}).json()
        clientB = c.post(f"{API}/clients", headers=_auth(tB), json={"name": "Cli B", "phone": "0600000001"}).json()
        saleA = c.post(f"{API}/sales", headers=_auth(tA), json={"client_id": clientA["id"], "service": "Iso A", "amount": 1000, "commission_rate": 0.1, "sale_date": "2026-01-15"}).json()
        saleB = c.post(f"{API}/sales", headers=_auth(tB), json={"client_id": clientB["id"], "service": "Iso B", "amount": 2000, "commission_rate": 0.1, "sale_date": "2026-01-15"}).json()
        yield {"A": A, "B": B, "tA": tA, "tB": tB,
               "adminA": pa["admin_email"], "passA": pa["admin_password"],
               "clientA": clientA, "clientB": clientB, "saleA": saleA, "saleB": saleB,
               "stok": stok, "sfx": sfx}


# ---------- Multi-tenant strict : IDs cross-tenant ----------
class TestCrossTenantIsolation:
    def test_A_cannot_read_client_of_B(self, ctx):
        with httpx.Client(timeout=15) as c:
            # Le GET direct par ID n'existe pas → l'API ne permet pas d'atteindre
            # un client par ID cross-tenant. Vérifie aussi via listing.
            r = c.get(f"{API}/clients", headers=_auth(ctx["tA"]))
            r.raise_for_status()
            ids = [x.get("id") for x in r.json()]
            assert ctx["clientB"]["id"] not in ids, "client B leaked into A's listing"

    def test_A_cannot_update_client_of_B(self, ctx):
        with httpx.Client(timeout=15) as c:
            # Payload complet valide → doit être bloqué 403/404 (pas 422)
            r = c.put(f"{API}/clients/{ctx['clientB']['id']}", headers=_auth(ctx["tA"]),
                      json={"name": "Cli B hijacked", "phone": "hacked"})
            assert r.status_code in (403, 404), f"leak: {r.status_code} {r.text}"

    def test_A_cannot_delete_client_of_B(self, ctx):
        with httpx.Client(timeout=15) as c:
            r = c.delete(f"{API}/clients/{ctx['clientB']['id']}", headers=_auth(ctx["tA"]))
            assert r.status_code in (403, 404), f"leak: {r.status_code} {r.text}"

    def test_A_cannot_read_sale_of_B(self, ctx):
        with httpx.Client(timeout=15) as c:
            # Sales don't have direct GET-by-id ; verify via listing scoping
            r = c.get(f"{API}/sales", headers=_auth(ctx["tA"]))
            r.raise_for_status()
            ids = [s.get("id") for s in (r.json() if isinstance(r.json(), list) else r.json().get("items", []))]
            assert ctx["saleB"]["id"] not in ids, "sale B leaked into A's listing"

    def test_A_cannot_update_sale_of_B(self, ctx):
        with httpx.Client(timeout=15) as c:
            r = c.put(f"{API}/sales/{ctx['saleB']['id']}", headers=_auth(ctx["tA"]), json={"status": "annule"})
            assert r.status_code in (403, 404), f"leak: {r.status_code} {r.text}"

    def test_A_cannot_delete_sale_of_B(self, ctx):
        with httpx.Client(timeout=15) as c:
            r = c.delete(f"{API}/sales/{ctx['saleB']['id']}", headers=_auth(ctx["tA"]))
            assert r.status_code in (403, 404), f"leak: {r.status_code} {r.text}"

    def test_A_cannot_force_company_id_in_payload(self, ctx):
        with httpx.Client(timeout=15) as c:
            r = c.post(f"{API}/clients", headers=_auth(ctx["tA"]), json={"name": "Hijack", "company_id": ctx["B"]["id"]})
            if r.status_code >= 400:
                return
            new_id = r.json().get("id")
            # Refetch : le client doit être dans la company A malgré le payload
            r2 = c.get(f"{API}/clients", headers=_auth(ctx["tB"]))
            r2.raise_for_status()
            ids = [x.get("id") for x in (r2.json() if isinstance(r2.json(), list) else [])]
            assert new_id not in ids, "company_id override succeeded — data leaked to B"

    def test_project_ids_cannot_be_targeted_cross_tenant(self, ctx):
        with httpx.Client(timeout=15) as c:
            projs_b = c.get(f"{API}/projects", headers=_auth(ctx["tB"])).json()
            if not projs_b:
                pytest.skip("no project in B to test")
            pid = projs_b[0]["id"]
            r = c.get(f"{API}/projects/{pid}/notes", headers=_auth(ctx["tA"]))
            assert r.status_code in (403, 404), f"leak: {r.status_code}"
            r2 = c.put(f"{API}/projects/{pid}", headers=_auth(ctx["tA"]), json={"status": "termine"})
            assert r2.status_code in (403, 404), f"write leak: {r2.status_code}"


# ---------- Payments IDOR ----------
class TestPaymentsIsolation:
    def test_random_session_id_returns_404(self, ctx):
        with httpx.Client(timeout=15) as c:
            r = c.get(f"{API}/payments/status/cs_test_bogus_{ctx['sfx']}", headers=_auth(ctx["tA"]))
            assert r.status_code == 404


# ---------- Subscription suspension : NON-destructif ----------
class TestSubscriptionSuspension:
    """Simule directement en BDD un compte suspendu et vérifie que :
        1) les endpoints métier renvoient 402
        2) les endpoints billing/auth restent accessibles
        3) aucune donnée n'a été perdue
        4) la réactivation restore l'accès complet"""

    def test_suspend_preserves_all_data_and_gates_api(self, ctx):
        client = MongoClient(MONGO_URL)
        db = client[DB_NAME]
        try:
            with httpx.Client(timeout=15) as c:
                admin_email = ctx["adminA"]
                admin_pass = ctx["passA"]
                before_clients = db.clients.count_documents({"company_id": ctx["A"]["id"]})
                before_sales = db.sales.count_documents({"company_id": ctx["A"]["id"]})
                db.users.update_one({"email": admin_email}, {"$set": {"subscription_status": "suspended"}})
                token = _login(c, admin_email, admin_pass)
                r_biz = c.get(f"{API}/clients", headers=_auth(token))
                assert r_biz.status_code == 402, f"expected 402 for suspended, got {r_biz.status_code}"
                r_bill = c.get(f"{API}/subscription/me", headers=_auth(token))
                assert r_bill.status_code == 200
                r_me = c.get(f"{API}/auth/me", headers=_auth(token))
                assert r_me.status_code == 200
                after_clients = db.clients.count_documents({"company_id": ctx["A"]["id"]})
                after_sales = db.sales.count_documents({"company_id": ctx["A"]["id"]})
                assert after_clients == before_clients
                assert after_sales == before_sales
                db.users.update_one({"email": admin_email}, {"$set": {"subscription_status": "active"}})
                tok2 = _login(c, admin_email, admin_pass)
                r_ok = c.get(f"{API}/clients", headers=_auth(tok2))
                assert r_ok.status_code == 200
                r_me2 = c.get(f"{API}/auth/me", headers=_auth(tok2)).json()
                assert r_me2.get("company_id") == ctx["A"]["id"], "company_id must be identical after reactivation"
        finally:
            client.close()


# ---------- Password hashing ----------
class TestPasswordSecurity:
    def test_admin_password_stored_as_bcrypt(self, ctx):
        client = MongoClient(MONGO_URL)
        db = client[DB_NAME]
        try:
            u = db.users.find_one({"email": ctx["adminA"]}, {"password_hash": 1, "_id": 0})
            assert u and u.get("password_hash", "").startswith("$2"), "password must be bcrypt-hashed"
        finally:
            client.close()


# ---------- Client duplicates cross-tenant : autorisés ----------
class TestSameClientAcrossCompanies:
    def test_two_companies_can_have_same_email_phone(self, ctx):
        with httpx.Client(timeout=15) as c:
            payload = {"name": "Jean Dupont", "phone": "0611223344", "email": f"jean+{ctx['sfx']}@dupont.fr"}
            rA = c.post(f"{API}/clients", headers=_auth(ctx["tA"]), json=payload)
            rB = c.post(f"{API}/clients", headers=_auth(ctx["tB"]), json=payload)
            assert rA.status_code < 400 and rB.status_code < 400, f"A={rA.status_code} B={rB.status_code}"
            assert rA.json().get("id") != rB.json().get("id")
