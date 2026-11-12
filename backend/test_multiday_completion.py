"""Régression : dernière journée multi-jours avec une nouvelle photo.

Le bug corrigé : la dernière journée poussait ses photos une première fois dans
days_done.<date>, puis la finalisation tentait de les pousser une seconde fois.
Le filtre anti-doublon faisait échouer cette seconde écriture et le chantier ne
passait jamais à « termine ».
"""

import asyncio
import os
import unittest
from concurrent.futures import ThreadPoolExecutor

os.environ.update({
    "ENVIRONMENT": "production",
    "MONGO_URL": "mongodb://127.0.0.1:27017",
    "DB_NAME": "kylot_multiday_test",
    "JWT_SECRET": "multiday-test-secret-at-least-32-characters",
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

PHOTO_1 = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
PHOTO_2 = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAusB9Y9Zl1sAAAAASUVORK5CYII="


class MultiDayCompletionTests(unittest.TestCase):
    def setUp(self):
        self.mongo = AsyncMongoMockClient()
        self.db = self.mongo["kylot_multiday_test"]
        server.db = self.db
        server.client = self.mongo
        self.client = TestClient(server.app)
        self.admin = {
            "id": "admin-md", "email": "admin-md@example.com", "name": "Admin MD",
            "password_hash": server.hash_password("multiday-password-123"),
            "role": "admin", "company_id": "company-md",
            "permissions": server.get_default_permissions("admin"),
        }
        asyncio.run(self.db.users.insert_one(self.admin))
        asyncio.run(self.db.projects.insert_one({
            "id": "project-md", "company_id": "company-md", "client_id": "client-md",
            "assigned_to": [], "status": "en_cours", "scheduled_date": "2026-11-01",
            "duration_days": 2, "photos": [], "days_done": {},
        }))
        self.headers = {"Authorization": "Bearer " + server.create_access_token(self.admin["id"], self.admin["email"])}

    def tearDown(self):
        self.client.close()
        self.mongo.close()

    def _complete(self, day, photo, note):
        return self.client.post(
            "/api/projects/project-md/complete",
            headers=self.headers,
            json={"photos": [photo], "day": day, "note": note},
        )

    def test_last_day_with_new_photo_finishes_and_keeps_two_unique_photos(self):
        first = self._complete("2026-11-01", PHOTO_1, "Jour 1")
        self.assertEqual(first.status_code, 200, first.text)
        self.assertTrue(first.json().get("partial"))
        second = self._complete("2026-11-02", PHOTO_2, "Jour 2")
        self.assertEqual(second.status_code, 200, second.text)
        self.assertFalse(second.json().get("partial"))

        project = asyncio.run(self.db.projects.find_one({"id": "project-md"}, {"_id": 0}))
        self.assertEqual(project["status"], "termine")
        srcs = [p["src"] if isinstance(p, dict) else p for p in project.get("photos", [])]
        self.assertEqual(len(srcs), 2)
        self.assertEqual(len(set(srcs)), 2)
        self.assertEqual(set(project.get("days_done", {}).keys()), {"2026-11-01", "2026-11-02"})

    def test_replaying_a_day_does_not_duplicate_photo_or_block_finalization(self):
        first = self._complete("2026-11-01", PHOTO_1, "Jour 1")
        self.assertEqual(first.status_code, 200, first.text)
        replay = self._complete("2026-11-01", PHOTO_1, "Jour 1 rejoué")
        self.assertEqual(replay.status_code, 200, replay.text)
        second = self._complete("2026-11-02", PHOTO_2, "Jour 2")
        self.assertEqual(second.status_code, 200, second.text)
        project = asyncio.run(self.db.projects.find_one({"id": "project-md"}, {"_id": 0}))
        self.assertEqual(project["status"], "termine")
        self.assertEqual(len(project.get("photos", [])), 2)


    def test_two_days_validated_concurrently_finish_with_two_photos(self):
        from concurrent.futures import ThreadPoolExecutor
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [
                pool.submit(self._complete, "2026-11-01", PHOTO_1, "Jour 1 parallèle"),
                pool.submit(self._complete, "2026-11-02", PHOTO_2, "Jour 2 parallèle"),
            ]
            responses = [f.result() for f in futures]
        self.assertEqual([r.status_code for r in responses], [200, 200], [r.text for r in responses])
        project = asyncio.run(self.db.projects.find_one({"id": "project-md"}, {"_id": 0}))
        self.assertEqual(project["status"], "termine")
        self.assertEqual(len(project.get("photos", [])), 2)
        self.assertEqual(len(project.get("days_done", {})), 2)

    def test_completion_rejects_photo_above_global_limit(self):
        asyncio.run(self.db.projects.update_one(
            {"id": "project-md"},
            {"$set": {"photos": [{"src": f"data:image/png;base64,AAAA{i}"} for i in range(server.MAX_PHOTOS_PER_ENTITY)]}},
        ))
        response = self._complete("2026-11-01", PHOTO_1, "Jour 1 trop de photos")
        self.assertEqual(response.status_code, 413, response.text)
        project = asyncio.run(self.db.projects.find_one({"id": "project-md"}, {"_id": 0}))
        self.assertEqual(project["status"], "en_cours")
        self.assertEqual(len(project.get("photos", [])), server.MAX_PHOTOS_PER_ENTITY)

    def test_already_present_photo_does_not_block_finalization(self):
        asyncio.run(self.db.projects.update_one(
            {"id": "project-md"}, {"$set": {"photos": [{"src": PHOTO_1}]}},
        ))
        first = self._complete("2026-11-01", PHOTO_1, "Jour 1 photo existante")
        second = self._complete("2026-11-02", PHOTO_1, "Jour 2 photo existante")
        self.assertEqual(first.status_code, 200, first.text)
        self.assertEqual(second.status_code, 200, second.text)
        project = asyncio.run(self.db.projects.find_one({"id": "project-md"}, {"_id": 0}))
        self.assertEqual(project["status"], "termine")
        self.assertEqual(len(project.get("photos", [])), 1)


if __name__ == "__main__":
    unittest.main()
