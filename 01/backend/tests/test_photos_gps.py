"""Photos GPS regression: PUT /api/projects must accept rich {src,lat,lng} photo objects."""
import os
import pytest
import requests
from dotenv import dotenv_values

BASE_URL = (os.environ.get("REACT_APP_BACKEND_URL") or dotenv_values("/app/frontend/.env")["REACT_APP_BACKEND_URL"]).rstrip("/")

TINY_PNG = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8DwHwAFAAH/q842iQAAAABJRU5ErkJggg=="


class TestProjectPhotosGps:
    def test_put_rich_photo_object_accepted(self, admin_client):
        projects = admin_client.get(f"{BASE_URL}/api/projects", timeout=30).json()
        assert projects, "no projects to test"
        p = projects[0]
        original = p.get("photos") or []
        payload = {"photos": [TINY_PNG, {"src": TINY_PNG, "lat": 50.72, "lng": 3.16, "taken_at": "2026-08-27T10:00:00Z"}]}
        try:
            r = admin_client.put(f"{BASE_URL}/api/projects/{p['id']}", json=payload, timeout=30)
            assert r.status_code == 200, f"rich photo object rejected: {r.status_code} {r.text[:300]}"
            got = admin_client.get(f"{BASE_URL}/api/projects", timeout=30).json()
            row = [x for x in got if x["id"] == p["id"]][0]
            assert isinstance(row["photos"][1], dict), row["photos"][1]
            assert row["photos"][1]["lat"] == 50.72
        finally:
            admin_client.put(f"{BASE_URL}/api/projects/{p['id']}", json={"photos": original}, timeout=30)
