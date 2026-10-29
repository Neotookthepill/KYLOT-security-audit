import asyncio, json, sys
from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import dotenv_values

env = dotenv_values("/app/backend/.env")
TINY = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8DwHwAFAAH/q842iQAAAABJRU5ErkJggg=="

async def main():
    mode = sys.argv[1]
    cl = AsyncIOMotorClient(env["MONGO_URL"])
    db = cl[env["DB_NAME"]]
    proj = await db.projects.find_one({}, {"_id": 0})
    print("project", proj["id"], "photos_before", len(proj.get("photos") or []))
    if mode == "seed":
        await db.projects.update_one({"id": proj["id"]}, {"$set": {"photos": [
            TINY,
            {"src": TINY, "lat": 50.7239, "lng": 3.1611, "taken_at": "2026-08-27T10:00:00Z"},
        ]}})
        print("SEEDED", proj["id"])
    else:
        await db.projects.update_one({"id": proj["id"]}, {"$set": {"photos": []}})
        print("CLEANED", proj["id"])

asyncio.run(main())
