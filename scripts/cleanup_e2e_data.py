#!/usr/bin/env python3
"""Delete only KYLOT staging data created by the E2E suites.

Usage (staging only):
  read -s MONGO_URL
  export MONGO_URL
  export DB_NAME=kylot_staging
  export DRY_RUN=1
  python scripts/cleanup_e2e_data.py

  # after checking the counts
  export KYLOT_ALLOW_E2E_CLEANUP=I_UNDERSTAND_THIS_DELETES_E2E_TEST_DATA
  export DRY_RUN=0
  python scripts/cleanup_e2e_data.py

The script never touches the default company, the real admin, or non-E2E data.
"""
import os
import re
import sys

from pymongo import MongoClient

MONGO_URL = os.environ.get("MONGO_URL")
DB_NAME = os.environ.get("DB_NAME", "kylot_staging")
DRY_RUN = (os.environ.get("DRY_RUN") or "1").strip().lower() in ("1", "true", "yes")
ACK = os.environ.get("KYLOT_ALLOW_E2E_CLEANUP") == "I_UNDERSTAND_THIS_DELETES_E2E_TEST_DATA"
if not MONGO_URL:
    print("MONGO_URL manquant", file=sys.stderr)
    sys.exit(2)

client = MongoClient(MONGO_URL, serverSelectionTimeoutMS=15000)
db = client[DB_NAME]

def ids_for(collection, query, field="id"):
    return [row[field] for row in collection.find(query, {"_id": 0, field: 1}) if row.get(field)]

clients = list(db.clients.find({"name": {"$regex": r"^E2E-", "$options": "i"}}, {"_id": 0, "id": 1, "name": 1}))
client_ids = [c["id"] for c in clients if c.get("id")]
sales_query = {"$or": [
    {"service": {"$regex": r"^E2E( |$)", "$options": "i"}},
    {"client_id": {"$in": client_ids}},
]}
sales = list(db.sales.find(sales_query, {"_id": 0, "id": 1, "service": 1}))
sale_ids = [s["id"] for s in sales if s.get("id")]
projects_query = {"$or": [
    {"sale_id": {"$in": sale_ids}},
    {"client_id": {"$in": client_ids}},
    {"service": {"$regex": r"^E2E( |$)", "$options": "i"}},
]}
projects = list(db.projects.find(projects_query, {"_id": 0, "id": 1}))
challenges = list(db.challenges.find({"name": {"$regex": r"^E2E Challenge", "$options": "i"}}, {"_id": 0, "id": 1}))
events = list(db.events.find({"title": {"$regex": r"^E2E-EVENT", "$options": "i"}}, {"_id": 0, "id": 1}))
users = list(db.users.find(
    {"email": {"$in": ["e2e-admin@kylot-audit.fr", "e2e-commercial@kylot-audit.fr"]}},
    {"_id": 0, "id": 1, "email": 1},
))
user_ids = [u["id"] for u in users if u.get("id")]

print(f"Base: {DB_NAME}")
print(f"Mode: {'DRY-RUN (aucune suppression)' if DRY_RUN else 'SUPPRESSION'}")
print(f"Clients E2E: {len(clients)}")
print(f"Ventes E2E: {len(sales)}")
print(f"Chantiers E2E: {len(projects)}")
print(f"Challenges E2E: {len(challenges)}")
print(f"Événements E2E: {len(events)}")
print(f"Comptes de test: {len(users)}")

if DRY_RUN:
    print("DRY_RUN=1 : rien n'a été supprimé.")
    client.close()
    sys.exit(0)
if not ACK:
    print("Suppression bloquée : KYLOT_ALLOW_E2E_CLEANUP manquant.", file=sys.stderr)
    client.close()
    sys.exit(3)

# Order matters: dependent rows before parents.
deleted = {}
if sale_ids:
    project_ids = [p["id"] for p in projects if p.get("id")]
    deleted["project_notes"] = db.project_notes.delete_many({"$or": [
        {"sale_id": {"$in": sale_ids}}, {"project_id": {"$in": project_ids}},
    ]}).deleted_count
    deleted["client_notes"] = db.client_notes.delete_many({"client_id": {"$in": client_ids}}).deleted_count
    deleted["projects"] = db.projects.delete_many({"id": {"$in": [p["id"] for p in projects]}}).deleted_count
    deleted["sales"] = db.sales.delete_many({"id": {"$in": sale_ids}}).deleted_count
else:
    deleted["projects"] = db.projects.delete_many({"id": {"$in": [p["id"] for p in projects]}}).deleted_count
    deleted["client_notes"] = db.client_notes.delete_many({"client_id": {"$in": client_ids}}).deleted_count

deleted["clients"] = db.clients.delete_many({"id": {"$in": client_ids}}).deleted_count
deleted["challenges"] = db.challenges.delete_many({"id": {"$in": [c["id"] for c in challenges]}}).deleted_count
deleted["events"] = db.events.delete_many({"id": {"$in": [e["id"] for e in events]}}).deleted_count
if user_ids:
    emails = [u.get("email") for u in users if u.get("email")]
    deleted["team_members"] = db.team_members.delete_many({"$or": [
        {"user_id": {"$in": user_ids}}, {"email": {"$in": emails}},
        {"name": {"$in": ["E2E Admin", "E2E Commercial"]}},
    ]}).deleted_count
    deleted["user_prefs"] = db.user_prefs.delete_many({"user_id": {"$in": user_ids}}).deleted_count
    deleted["users"] = db.users.delete_many({"id": {"$in": user_ids}}).deleted_count

print("Supprimés:", deleted)
print("Nettoyage E2E terminé.")
client.close()
