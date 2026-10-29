"""iter138 : vérification DB brute — un import ne doit modifier QUE la collection clients."""
import asyncio
import os
import random
import string

import requests
from dotenv import dotenv_values
from motor.motor_asyncio import AsyncIOMotorClient

benv = dotenv_values("/app/backend/.env")
fenv = dotenv_values("/app/frontend/.env")
BASE = (os.environ.get("REACT_APP_BACKEND_URL") or fenv["REACT_APP_BACKEND_URL"]).rstrip("/")
SFX = "".join(random.choices(string.ascii_lowercase, k=6))
TAG = f"TEST_DBSTRICT_{SFX}"


async def main():
    cli = AsyncIOMotorClient(benv["MONGO_URL"])
    db = cli[benv["DB_NAME"]]
    names = await db.list_collection_names()
    before = {n: await db[n].count_documents({}) for n in names}

    tok = requests.post(f"{BASE}/api/auth/login", json={
        "email": "admin@example.invalid", "password": "CHANGE_ME_TEST_PASSWORD"}, timeout=30).json()["token"]
    h = {"Authorization": f"Bearer {tok}", "Content-Type": "application/json"}
    rows = [[f"{TAG}_{i}", f"0777{i:06d}", f"{TAG}_{i}@test.fr"] for i in range(5)]
    r = requests.post(f"{BASE}/api/clients/import/execute", headers=h, json={
        "mapping": {"0": "name", "1": "phone", "2": "email"}, "rows": rows,
        "duplicate_strategy": "ignore"}, timeout=120)
    print("execute:", r.status_code, r.json().get("created_count"))

    names2 = await db.list_collection_names()
    after = {n: await db[n].count_documents({}) for n in names2}
    print("new collections:", sorted(set(names2) - set(names)))
    problems = []
    for n in sorted(set(names) | set(names2)):
        b, a = before.get(n, 0), after.get(n, 0)
        if b != a:
            print(f"  DELTA {n}: {b} -> {a}")
            if n != "clients":
                problems.append(n)
    print("PROBLEM COLLECTIONS:" , problems if problems else "NONE — seule `clients` a changé")

    # cleanup
    res = await db.clients.delete_many({"name": {"$regex": f"^{TAG}"}})
    print("cleaned clients:", res.deleted_count)
    leftover = await db.clients.count_documents({"name": {"$regex": "^TEST_IMP_"}})
    print("leftover TEST_IMP_ clients:", leftover)
    cli.close()


asyncio.run(main())
