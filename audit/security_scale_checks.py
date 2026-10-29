"""Bounded local scale checks for KYLOT.

Timings use mongomock and are regression smoke signals, not production capacity
claims. Real MongoDB/proxy/load testing remains mandatory on staging.
"""

from __future__ import annotations

import asyncio
import os
from time import perf_counter
import unittest


os.environ.update({
    "ENVIRONMENT": "production",
    "MONGO_URL": "mongodb://127.0.0.1:27017",
    "DB_NAME": "kylot_scale_checks",
    "JWT_SECRET": "scale-test-secret-at-least-32-characters",
    "FRONTEND_URL": "https://app.example.invalid",
    "CORS_ORIGINS": "https://app.example.invalid",
    "ALLOW_PUBLIC_REGISTRATION": "false",
    "ALLOW_DEMO_DATA": "false",
    "ALLOW_TOKEN_RESPONSE": "false",
    "RUN_STARTUP_MIGRATIONS": "false",
    "EXPOSE_API_DOCS": "false",
    "COOKIE_SECURE": "true",
    "COOKIE_SAMESITE": "lax",
})

from fastapi.testclient import TestClient
from mongomock_motor import AsyncMongoMockClient

from backend import server


def run(coro):
    return asyncio.run(coro)


class BoundedScaleChecks(unittest.TestCase):
    def setUp(self):
        self.mongo = AsyncMongoMockClient()
        self.db = self.mongo["kylot_scale_checks"]
        server.db = self.db
        server.client = self.mongo
        self.client = TestClient(server.app)
        self.admin = {
            "id": "admin-a", "email": "admin-a@example.invalid", "name": "Admin A",
            "role": "admin", "company_id": "company-a",
            "permissions": server.get_default_permissions("admin"),
        }
        run(self.db.users.insert_one(self.admin))
        token = server.create_access_token(self.admin["id"], self.admin["email"])
        self.headers = {"Authorization": f"Bearer {token}"}

    def tearDown(self):
        self.client.close()
        self.mongo.close()

    def timed(self, label, fn, *, max_seconds=15.0):
        started = perf_counter()
        result = fn()
        elapsed = perf_counter() - started
        print(f"SCALE {label}: {elapsed:.3f}s")
        self.assertLess(elapsed, max_seconds, f"{label} exceeded local smoke budget")
        return result

    def test_tenant_filter_with_ten_thousand_clients(self):
        docs = [
            {"id": f"client-a-{i}", "company_id": "company-a", "name": f"Client A {i}"}
            for i in range(5000)
        ] + [
            {"id": f"client-b-{i}", "company_id": "company-b", "name": f"Client B {i}"}
            for i in range(5000)
        ]
        run(self.db.clients.insert_many(docs))
        response = self.timed("list 5k tenant clients among 10k", lambda: self.client.get("/api/clients", headers=self.headers))
        self.assertEqual(response.status_code, 200, response.text)
        rows = response.json()
        self.assertEqual(len(rows), 5000)
        self.assertTrue(all(row["id"].startswith("client-a-") for row in rows))

    def test_streamed_export_with_five_thousand_sales(self):
        docs = [{
            "id": f"sale-a-{i}", "company_id": "company-a", "client_id": f"client-a-{i}",
            "client_name": f"Client {i}", "commercial": "Admin A", "service": "Service",
            "amount": i, "sale_date": "2026-10-01", "status": "en_cours",
        } for i in range(5000)]
        run(self.db.sales.insert_many(docs))
        response = self.timed("stream 5k sales CSV", lambda: self.client.get("/api/export/sales.csv", headers=self.headers))
        self.assertEqual(response.status_code, 200, response.text[:500])
        self.assertEqual(response.headers.get("content-type", "").split(";")[0], "text/csv")
        self.assertGreaterEqual(response.content.count(b"\n"), 5000)

    def test_import_parse_and_execute_one_thousand_clients(self):
        rows = ["name;phone;email"] + [
            f"Imported {i};060000{i:04d};imported-{i}@example.invalid" for i in range(1000)
        ]
        payload = ("\n".join(rows) + "\n").encode()
        parsed = self.timed(
            "parse 1k client CSV",
            lambda: self.client.post(
                "/api/clients/import/parse", headers=self.headers,
                files={"file": ("clients.csv", payload, "text/csv")},
            ),
        )
        self.assertEqual(parsed.status_code, 200, parsed.text)
        body = parsed.json()
        self.assertEqual(body["row_count"], 1000)
        self.assertEqual(len(body["preview"]), 20)
        self.assertNotIn("rows_full", body)
        executed = self.timed(
            "execute 1k client import",
            lambda: self.client.post(
                "/api/clients/import/execute", headers=self.headers,
                json={"import_id": body["import_id"], "mapping": {"0": "name", "1": "phone", "2": "email"}},
            ),
            max_seconds=25.0,
        )
        self.assertEqual(executed.status_code, 200, executed.text)
        self.assertEqual(len(executed.json()["created"]), 1000)
        self.assertEqual(run(self.db.clients.count_documents({"company_id": "company-a"})), 1000)

    def test_import_rejects_more_than_the_configured_row_limit(self):
        rows = ["name"] + [f"Client {i}" for i in range(server.MAX_IMPORT_ROWS + 1)]
        payload = ("\n".join(rows) + "\n").encode()
        response = self.timed(
            "reject oversized row-count CSV",
            lambda: self.client.post(
                "/api/clients/import/parse", headers=self.headers,
                files={"file": ("too-many.csv", payload, "text/csv")},
            ),
        )
        self.assertEqual(response.status_code, 413, response.text)
        self.assertEqual(run(self.db.client_import_batches.count_documents({})), 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
