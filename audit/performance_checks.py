"""Local performance smoke test on a disposable Mongo-compatible store.

This measures application and serialization time, not MongoDB/network time.
Run: PYTHONPATH=. ./.venv/bin/python audit/performance_checks.py
"""

import asyncio
import os
import statistics
import time

os.environ.update({
    "ENVIRONMENT": "test",
    "MONGO_URL": "mongodb://127.0.0.1:27017",
    "DB_NAME": "kylot_perf_test",
    "JWT_SECRET": "performance-test-key-9a4c2e7b1d8f6a3c",
    "FRONTEND_URL": "https://app.example.invalid",
    "CORS_ORIGINS": "https://app.example.invalid",
    "ALLOW_PUBLIC_REGISTRATION": "false",
    "ALLOW_DEMO_DATA": "false",
    "ALLOW_TOKEN_RESPONSE": "false",
    "RUN_STARTUP_MIGRATIONS": "false",
    "EXPOSE_API_DOCS": "false",
    "COOKIE_SECURE": "true",
    "COOKIE_SAMESITE": "lax",
    "ADMIN_EMAIL": "admin@example.com",
    "ADMIN_PASSWORD": "V7!mQ2#pL9$xR4@t",
})

from fastapi.testclient import TestClient
from mongomock_motor import AsyncMongoMockClient

from backend import server

CLIENTS = int(os.environ.get("PERF_CLIENTS", "5000"))
SALES = int(os.environ.get("PERF_SALES", "5000"))
PROJECTS = int(os.environ.get("PERF_PROJECTS", "20000"))
AUDIT = int(os.environ.get("PERF_AUDIT", "5000"))


def run(coro):
    return asyncio.run(coro)


async def seed(db):
    admin = {
        "id": "perf-admin", "email": "admin@example.com", "name": "Perf Admin",
        "role": "admin", "company_id": "perf-company",
        "permissions": server.get_default_permissions("admin"),
        "password_hash": server.hash_password("V7!mQ2#pL9$xR4@t"),
        "is_active": True,
    }
    await db.users.insert_one(admin)
    await db.companies.insert_one({"id": "perf-company", "name": "Perf Company"})

    clients = [
        {"id": f"c-{i}", "company_id": "perf-company", "name": f"Client {i:05d}",
         "phone": f"0600{i:06d}", "email": f"client{i}@example.com",
         "address": f"{i} rue de Paris", "postal_code": "75000", "city": "Paris",
         "categories": [{"category_key": "vip" if i % 3 == 0 else "standard"}],
         "created_by": admin["id"], "created_at": f"2026-01-{(i % 28) + 1:02d}T00:00:00Z"}
        for i in range(CLIENTS)
    ]
    sales = [
        {"id": f"s-{i}", "company_id": "perf-company", "client_id": f"c-{i % CLIENTS}",
         "amount": 500 + (i % 20) * 100, "status": "en_cours" if i % 7 else "annule",
         "sale_date": f"2026-{(i % 12) + 1:02d}-{(i % 28) + 1:02d}", "commercial": "Perf Admin",
         "source": "R1", "payment_method": "cheque", "created_at": f"2026-01-{(i % 28) + 1:02d}T00:00:00Z"}
        for i in range(SALES)
    ]
    projects = [
        {"id": f"p-{i}", "company_id": "perf-company", "sale_id": f"s-{i % SALES}",
         "client_id": f"c-{i % CLIENTS}", "assigned_to": ["Perf Tech"],
         "status": "en_cours", "scheduled_date": f"2026-{(i % 12) + 1:02d}-15",
         "cancelled": False, "created_at": f"2026-01-{(i % 28) + 1:02d}T00:00:00Z"}
        for i in range(PROJECTS)
    ]
    audits = [
        {"id": f"a-{i}", "company_id": "perf-company", "user_id": admin["id"],
         "user_name": "Perf Admin", "user_role": "admin", "action": "update",
         "resource": "client", "resource_id": f"c-{i % CLIENTS}",
         "at": f"2026-01-{(i % 28) + 1:02d}T00:00:00Z"}
        for i in range(AUDIT)
    ]
    for name, rows in (("clients", clients), ("sales", sales), ("projects", projects), ("audit_log", audits)):
        for start in range(0, len(rows), 1000):
            await db[name].insert_many(rows[start:start + 1000])
    return admin


def measure(client, method, path, headers):
    times = []
    last = None
    for _ in range(3):
        start = time.perf_counter()
        last = client.request(method, path, headers=headers)
        times.append((time.perf_counter() - start) * 1000)
    return last, statistics.median(times)


def main():
    mongo = AsyncMongoMockClient()
    db = mongo["kylot_perf_test"]
    server.db = db
    server.client = mongo
    admin = run(seed(db))
    token = server.create_access_token(admin["id"], admin["email"])
    headers = {"Authorization": f"Bearer {token}"}
    client = TestClient(server.app, base_url="https://testserver")
    checks = [
        ("clients page", "GET", "/api/clients?limit=100&offset=0"),
        ("clients search", "GET", "/api/clients?q=Client%2001234&limit=100"),
        ("clients counts", "GET", "/api/clients/category-counts"),
        ("sales page", "GET", "/api/sales?limit=100&offset=0&from_date=2026-01-01&to_date=2026-12-31"),
        ("sales summary", "GET", "/api/sales/summary?from_date=2026-01-01&to_date=2026-12-31"),
        ("projects page", "GET", "/api/projects?limit=100&offset=0"),
        ("audit page", "GET", "/api/audit?limit=100&offset=0"),
    ]
    try:
        print(f"Jeu de données: {CLIENTS} clients, {SALES} ventes, {PROJECTS} chantiers, {AUDIT} audits")
        print(f"{'Mesure':24} {'HTTP':>5} {'médiane ms':>12}")
        for label, method, path in checks:
            response, ms = measure(client, method, path, headers)
            print(f"{label:24} {response.status_code:>5} {ms:>12.1f}")
            assert response.status_code == 200, (label, response.text[:300])
        print("Performance smoke test: OK")
    finally:
        client.close()
        mongo.close()


if __name__ == "__main__":
    main()
