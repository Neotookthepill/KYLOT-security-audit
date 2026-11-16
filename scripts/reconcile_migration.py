#!/usr/bin/env python3
"""Contrôle read-only d'une migration Qylot.

Aucun POST/PUT/DELETE. Aucune donnée personnelle n'est affichée : uniquement
des volumes, des codes et des compteurs d'anomalies.

Variables :
  KYLOT_BASE_URL       ex. https://kylot-preview.onrender.com
  KYLOT_ADMIN_EMAIL
  KYLOT_ADMIN_PASSWORD
  KYLOT_SOURCE_EXPORT  optionnel, dossier source exporté (clients.json, ...)
"""
import json
import os
import re
import sys
import urllib.parse
import urllib.request
import http.cookiejar
from collections import Counter

BASE = (os.environ.get("KYLOT_BASE_URL") or "").rstrip("/")
EMAIL = os.environ.get("KYLOT_ADMIN_EMAIL") or ""
PASSWORD = os.environ.get("KYLOT_ADMIN_PASSWORD") or ""
SOURCE = os.environ.get("KYLOT_SOURCE_EXPORT") or ""

if not BASE or not EMAIL or not PASSWORD:
    print("ERREUR: KYLOT_BASE_URL, KYLOT_ADMIN_EMAIL et KYLOT_ADMIN_PASSWORD sont requis.", file=sys.stderr)
    sys.exit(2)

jar = http.cookiejar.CookieJar()
opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))


def request(path, method="GET", body=None):
    data = None if body is None else json.dumps(body).encode()
    req = urllib.request.Request(BASE + path, data=data, method=method,
                                 headers={"Content-Type": "application/json"})
    with opener.open(req, timeout=60) as response:
        return response.status, json.loads(response.read().decode() or "null")


def load_source(name):
    if not SOURCE:
        return []
    try:
        with open(os.path.join(SOURCE, name + ".json"), encoding="utf-8") as fh:
            value = json.load(fh)
        return value if isinstance(value, list) else []
    except Exception:
        return []


def norm(value):
    return re.sub(r"\s+", " ", str(value or "").strip().lower())


def main():
    status, version = request("/api/version")
    _, health = request("/api/health")
    _, ready = request("/api/ready")
    request("/api/auth/login", "POST", {"email": EMAIL, "password": PASSWORD})

    clients = request("/api/clients?limit=5000")[1]
    sales = request("/api/sales?limit=5000")[1]
    projects = request("/api/projects?limit=5000")[1]
    events = request("/api/events")[1]
    stock = request("/api/stock")[1]
    team = request("/api/team")[1]
    users = request("/api/users")[1]

    src_clients = load_source("clients")
    src_sales = load_source("sales")
    src_projects = load_source("projects")
    src_users = load_source("users")
    src_team = load_source("team")

    errors, warnings = [], []
    if not isinstance(clients, list) or not isinstance(sales, list) or not isinstance(projects, list):
        print("ERREUR: réponse API inattendue", file=sys.stderr)
        return 2

    cids = {c.get("id") for c in clients}
    sids = {s.get("id") for s in sales}
    dup_email = [v for v, n in Counter(norm(c.get("email")) for c in clients if c.get("email")).items() if n > 1]
    dup_phone = [v for v, n in Counter(norm(c.get("phone")) for c in clients if c.get("phone")).items() if n > 1]
    dup_bdc = [v for v, n in Counter(norm(s.get("bdc")) for s in sales if s.get("bdc")).items() if n > 1]
    orphan_sale_client = sum(1 for s in sales if s.get("client_id") and s["client_id"] not in cids)
    orphan_project_client = sum(1 for p in projects if p.get("client_id") and p["client_id"] not in cids)
    orphan_project_sale = sum(1 for p in projects if p.get("sale_id") and p["sale_id"] not in sids)
    test_objects = sum(1 for row in clients + sales + projects if str(row.get("name") or row.get("client_name") or "").startswith("TEST-AUDIT"))
    photos = sum(len(p.get("photos") or []) for p in projects)

    if dup_email: errors.append("doublons email client: %d" % len(dup_email))
    if dup_phone: errors.append("doublons téléphone client: %d" % len(dup_phone))
    if orphan_sale_client: errors.append("ventes sans client: %d" % orphan_sale_client)
    if orphan_project_client: errors.append("chantiers sans client: %d" % orphan_project_client)
    if orphan_project_sale: errors.append("chantiers sans vente: %d" % orphan_project_sale)
    if test_objects: errors.append("objets TEST-AUDIT en production: %d" % test_objects)
    if dup_bdc: warnings.append("BDC dupliqués existants: %d" % len(dup_bdc))

    if src_clients and len(clients) < len(src_clients): errors.append("clients cible < source")
    if src_sales and len(sales) < len(src_sales): errors.append("ventes cible < source")
    if src_projects and len(projects) < len(src_projects): errors.append("chantiers cible < source")

    if src_users:
        target_emails = {norm(u.get("email")) for u in users if u.get("email")}
        missing = sum(1 for u in src_users if u.get("email") and norm(u["email"]) not in target_emails)
        if missing: errors.append("emails utilisateurs source absents: %d" % missing)
    if src_team:
        target_names = {norm(t.get("name")) for t in team if t.get("name")}
        missing = sum(1 for t in src_team if t.get("name") and norm(t["name"]) not in target_names)
        if missing: warnings.append("libellés équipe source absents: %d" % missing)

    result = {
        "version": version.get("version") if isinstance(version, dict) else None,
        "health": health,
        "ready": ready,
        "counts": {"clients": len(clients), "sales": len(sales), "projects": len(projects),
                   "events": len(events) if isinstance(events, list) else None,
                   "stock": len(stock) if isinstance(stock, list) else None,
                   "team": len(team) if isinstance(team, list) else None,
                   "users": len(users) if isinstance(users, list) else None,
                   "photos": photos},
        "duplicates": {"client_email": len(dup_email), "client_phone": len(dup_phone), "sale_bdc": len(dup_bdc)},
        "orphans": {"sale_client": orphan_sale_client, "project_client": orphan_project_client, "project_sale": orphan_project_sale},
        "test_objects": test_objects,
        "warnings": warnings,
        "errors": errors,
        "ok": not errors,
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if not errors else 1


if __name__ == "__main__":
    sys.exit(main())
