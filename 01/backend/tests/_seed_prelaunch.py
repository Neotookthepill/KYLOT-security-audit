"""Seed / cleanup helper for the iteration-14 pre-launch UI tests.

Usage:
  python _seed_prelaunch.py seed
  python _seed_prelaunch.py clean
"""
import sys
from datetime import datetime, timedelta, timezone

import requests
from dotenv import dotenv_values

BASE = dotenv_values("/app/frontend/.env")["REACT_APP_BACKEND_URL"].rstrip("/") + "/api"
SUPER = ("super@keylot.app", "Super@2026")
ALPHA_NAME = "TEST_Alpha SARL"
BETA_NAME = "TEST_Beta SAS"
TODAY = datetime.now(timezone.utc).date()
TOMORROW = (TODAY + timedelta(days=1)).isoformat()


def sess(email, pwd):
    r = requests.post(f"{BASE}/auth/login", json={"email": email, "password": pwd}, timeout=30)
    r.raise_for_status()
    s = requests.Session()
    s.headers.update({"Authorization": f"Bearer {r.json()['token']}", "Content-Type": "application/json"})
    return s


def clean(su):
    for c in su.get(f"{BASE}/superadmin/companies", timeout=30).json():
        if c["name"] in (ALPHA_NAME, BETA_NAME):
            su.delete(f"{BASE}/superadmin/companies/{c['id']}", timeout=30)
            print("deleted", c["name"])


def seed(su):
    clean(su)
    ids = {}
    for name, email, pwd in ((ALPHA_NAME, "alpha-admin@keylot.example.com", "Alpha@2026"),
                             (BETA_NAME, "beta-admin@keylot.example.com", "Beta@2026")):
        r = su.post(f"{BASE}/superadmin/companies", json={
            "name": name, "admin_email": email, "admin_password": pwd, "admin_name": name + " Admin"}, timeout=30)
        r.raise_for_status()
        ids[name] = r.json()["company"]["id"]
    a = sess("alpha-admin@keylot.example.com", "Alpha@2026")
    users = [("theo.alpha@keylot.example.com", "Theo@2026", "Théo", "commercial"),
             ("lea.alpha@keylot.example.com", "Lea@2026", "Léa", "commercial"),
             ("seb.alpha@keylot.example.com", "Seb@2026", "Sébastien", "technicien"),
             ("lucas.alpha@keylot.example.com", "Lucas@2026", "Lucas", "technicien"),
             ("marc.alpha@keylot.example.com", "Marc@2026", "Marc", "technicien"),
             ("resp.alpha@keylot.example.com", "Resp@2026", "Responsable Alpha", "responsable")]
    for email, pwd, nm, role in users:
        a.post(f"{BASE}/users", json={"email": email, "password": pwd, "name": nm, "role": role}, timeout=30).raise_for_status()
    for nm, t in (("Théo", "commercial"), ("Léa", "commercial"), ("Sébastien", "technicien"),
                  ("Lucas", "technicien"), ("Marc", "technicien")):
        a.post(f"{BASE}/team", json={"name": nm, "type": t, "objectif": 20000}, timeout=30).raise_for_status()
    t = sess("theo.alpha@keylot.example.com", "Theo@2026")
    for cname, amount in (("Dupont", 5000), ("Martin", 8000)):
        c = t.post(f"{BASE}/clients", json={"name": cname, "phone": "0600000000", "city": "Lyon",
                                            "address": "1 rue des Tests", "postal_code": "69000"}, timeout=30)
        c.raise_for_status()
        s = t.post(f"{BASE}/sales", json={"client_id": c.json()["id"], "service": "Isolation", "amount": amount,
                                          "commission_rate": 0.10, "commercial": "Théo",
                                          "sale_date": TODAY.isoformat(), "status": "commercial_cheque"}, timeout=30)
        s.raise_for_status()
    projects = a.get(f"{BASE}/projects", timeout=30).json()
    for p, tech in zip(projects, ("Sébastien", "Lucas")):
        a.put(f"{BASE}/projects/{p['id']}", json={"assigned_to": [tech], "scheduled_date": TOMORROW,
                                                  "status": "en_cours"}, timeout=30).raise_for_status()
    seb = sess("seb.alpha@keylot.example.com", "Seb@2026")
    seb.post(f"{BASE}/overtime", json={"technician_name": "Sébastien", "date": TODAY.isoformat(), "hours": 2}, timeout=30).raise_for_status()
    print("seeded", ids)


if __name__ == "__main__":
    su = sess(*SUPER)
    if sys.argv[1] == "seed":
        seed(su)
    else:
        clean(su)
