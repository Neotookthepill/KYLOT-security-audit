import asyncio
import os
import unittest

os.environ.update({
    "ENVIRONMENT": "development",
    "MONGO_URL": "mongodb://127.0.0.1:27017",
    "DB_NAME": "kylot_tenant_repo_test",
    "JWT_SECRET": "tenant-repo-test-key-5a4b8c2e9f1d7a3b",
    "FRONTEND_URL": "http://localhost:3000",
    "ADMIN_EMAIL": "admin@example.com",
    "ADMIN_PASSWORD": "V7!mQ2#pL9$xR4@t",
})

from mongomock_motor import AsyncMongoMockClient
from backend.tenant_repo import TenantIsolationError, TenantRepository


def run(coro):
    return asyncio.run(coro)


class TenantRepositoryTests(unittest.TestCase):
    def setUp(self):
        self.db = AsyncMongoMockClient()["proxy-test"]
        self.a = TenantRepository(self.db, {"id": "ua", "company_id": "a"})
        self.b = TenantRepository(self.db, {"id": "ub", "company_id": "b"})

    def test_insert_forces_company_and_lists_are_isolated(self):
        run(self.a.insert_one("clients", {"id": "ca", "name": "A"}))
        run(self.b.insert_one("clients", {"id": "cb", "name": "B"}))
        self.assertEqual([x["id"] for x in run(self.a.find("clients", {}).to_list(10))], ["ca"])
        self.assertEqual([x["id"] for x in run(self.b.find("clients", {}).to_list(10))], ["cb"])
        self.assertEqual(run(self.a.find_one("clients", {"id": "cb"})), None)

    def test_client_cannot_choose_company(self):
        run(self.b.insert_one("clients", {"id": "cb", "name": "B"}))
        with self.assertRaises(TenantIsolationError):
            run(self.a.insert_one("clients", {"id": "x", "company_id": "b"}))
        with self.assertRaises(TenantIsolationError):
            run(self.a.find_one("clients", {"company_id": "b"}))
        r = run(self.a.update_one("clients", {"id": "cb"}, {"$set": {"name": "hacked"}}))
        self.assertEqual(r.matched_count, 0)
        self.assertEqual(run(self.b.find_one("clients", {"id": "cb"}))["name"], "B")

    def test_update_delete_are_scoped(self):
        run(self.b.insert_one("clients", {"id": "cb", "name": "B"}))
        r = run(self.a.update_one("clients", {"id": "cb"}, {"$set": {"name": "hacked"}}))
        self.assertEqual(r.matched_count, 0)
        self.assertEqual(run(self.b.find_one("clients", {"id": "cb"}))["name"], "B")
        d = run(self.a.delete_one("clients", {"id": "cb"}))
        self.assertEqual(d.deleted_count, 0)
        self.assertIsNotNone(run(self.b.find_one("clients", {"id": "cb"})))

    def test_aggregate_always_starts_with_tenant_match(self):
        run(self.a.insert_one("sales", {"id": "sa", "amount": 10}))
        run(self.b.insert_one("sales", {"id": "sb", "amount": 99}))
        cursor = run(self.a.aggregate("sales", [{"$group": {"_id": None, "total": {"$sum": "$amount"}}}]))
        rows = run(cursor.to_list(10))
        self.assertEqual(rows[0]["total"], 10)


if __name__ == "__main__":
    unittest.main()
