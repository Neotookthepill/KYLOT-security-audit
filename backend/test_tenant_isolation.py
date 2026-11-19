"""Isolation multi-tenant : un compte ne doit jamais lire/modifier un autre client."""
import asyncio
import os
import unittest

os.environ.update({
    "ENVIRONMENT": "production",
    "MONGO_URL": "mongodb://127.0.0.1:27017",
    "DB_NAME": "kylot_tenant_isolation_test",
    "JWT_SECRET": "tenant-isolation-test-key-5a4b8c2e9f1d7a3b",
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


def run(coro):
    return asyncio.run(coro)


class TenantIsolationTests(unittest.TestCase):
    def setUp(self):
        self.mongo = AsyncMongoMockClient()
        self.db = self.mongo["kylot_tenant_isolation_test"]
        server.db = self.db
        server.client = self.mongo
        self.client = TestClient(server.app)
        self.a = "tenant-a"
        self.b = "tenant-b"
        self.admin_a = self._user("admin-a", "admin-a@example.com", "Admin A", self.a)
        self.admin_b = self._user("admin-b", "admin-b@example.com", "Admin B", self.b)
        run(self.db.users.insert_many([self.admin_a, self.admin_b]))
        run(self.db.companies.insert_many([
            {"id": self.a, "name": "A", "created_by": "system", "created_at": "2026-01-01T00:00:00Z"},
            {"id": self.b, "name": "B", "created_by": "system", "created_at": "2026-01-01T00:00:00Z"},
        ]))
        for company, suffix in ((self.a, "a"), (self.b, "b")):
            run(self.db.clients.insert_one({
                "id": f"client-{suffix}", "company_id": company, "name": f"Client {suffix}",
                "created_by": f"admin-{suffix}", "created_at": "2026-01-02T00:00:00Z",
            }))
            run(self.db.sales.insert_one({
                "id": f"sale-{suffix}", "company_id": company, "client_id": f"client-{suffix}",
                "client_name": f"Client {suffix}", "amount": 100, "status": "en_cours",
                "sale_date": "2026-01-03", "commercial": "Admin", "created_by": f"admin-{suffix}",
                "created_at": "2026-01-03T00:00:00Z",
            }))
            run(self.db.projects.insert_one({
                "id": f"project-{suffix}", "company_id": company, "sale_id": f"sale-{suffix}",
                "client_id": f"client-{suffix}", "status": "a_planifier", "created_at": "2026-01-03T00:00:00Z",
            }))
            run(self.db.stock.insert_one({
                "id": f"stock-{suffix}", "company_id": company, "product_name": f"Produit {suffix}",
                "product_key": f"produit-{suffix}", "stock_disponible": 1,
            }))
            run(self.db.overtime.insert_one({
                "id": f"ot-{suffix}", "company_id": company, "technician_name": "Tech",
                "date": "2026-01-04", "hours": 1, "status": "approved",
            }))
        self.headers_a = self._headers(self.admin_a)
        self.headers_b = self._headers(self.admin_b)

    def tearDown(self):
        self.client.close()
        self.mongo.close()

    def _user(self, uid, email, name, company):
        return {"id": uid, "email": email, "name": name, "role": "admin",
                "company_id": company, "permissions": server.get_default_permissions("admin")}

    @staticmethod
    def _headers(user):
        return {"Authorization": f"Bearer {server.create_access_token(user['id'], user['email'])}"}

    def test_clients_are_isolated(self):
        r = self.client.get("/api/clients?limit=100", headers=self.headers_a)
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual([x["id"] for x in r.json()], ["client-a"])

    def test_sales_and_projects_are_isolated(self):
        sales = self.client.get("/api/sales?limit=100", headers=self.headers_a)
        self.assertEqual(sales.status_code, 200, sales.text)
        self.assertEqual([x["id"] for x in sales.json()], ["sale-a"])
        projects = self.client.get("/api/projects?limit=100", headers=self.headers_a)
        self.assertEqual(projects.status_code, 200, projects.text)
        self.assertEqual([x["id"] for x in projects.json()], ["project-a"])

    def test_stock_and_overtime_are_isolated(self):
        stock = self.client.get("/api/stock", headers=self.headers_a)
        self.assertEqual(stock.status_code, 200, stock.text)
        self.assertEqual([x["id"] for x in stock.json()], ["stock-a"])
        overtime = self.client.get("/api/overtime?month=2026-01", headers=self.headers_a)
        self.assertEqual(overtime.status_code, 200, overtime.text)
        self.assertEqual([x["id"] for x in overtime.json().get("entries", [])], ["ot-a"])

    def test_cross_tenant_reads_and_writes_are_refused(self):
        r = self.client.get("/api/clients?client_id=client-b&limit=1", headers=self.headers_a)
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json(), [])
        r = self.client.get("/api/projects/project-b", headers=self.headers_a)
        self.assertIn(r.status_code, (403, 404), r.text)
        r = self.client.put("/api/sales/sale-b", json={"status": "annule"}, headers=self.headers_a)
        self.assertIn(r.status_code, (403, 404), r.text)
        r = self.client.put("/api/clients/client-b", json={"name": "Hacked"}, headers=self.headers_a)
        self.assertIn(r.status_code, (403, 404), r.text)
        # données B intactes
        self.assertEqual(run(self.db.clients.find_one({"id": "client-b"}))["name"], "Client b")
        self.assertEqual(run(self.db.sales.find_one({"id": "sale-b"}))["status"], "en_cours")


if __name__ == "__main__":
    unittest.main()
