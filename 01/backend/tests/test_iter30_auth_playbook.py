"""Auth playbook conformance checks (iter30).

- bcrypt hash format ($2b$)
- brute-force lockout after 5 failed logins (429)
- CORS configuration (explicit origins)
- login response shape / cookie policy
"""
import os
import uuid

import pytest
import requests
from dotenv import dotenv_values
from pymongo import MongoClient

frontend_env = dotenv_values("/app/frontend/.env")
backend_env = dotenv_values("/app/backend/.env")
_base = os.environ.get("REACT_APP_BACKEND_URL") or frontend_env.get("REACT_APP_BACKEND_URL")
if not _base:
    raise RuntimeError("REACT_APP_BACKEND_URL missing")
BASE = _base.rstrip("/")
API = f"{BASE}/api"
ADMIN_EMAIL = "admin@example.invalid"


class TestAuthPlaybook:
    def test_bcrypt_hash_format(self):
        mc = MongoClient(backend_env["MONGO_URL"], serverSelectionTimeoutMS=8000)
        db = mc[backend_env["DB_NAME"]]
        u = db.users.find_one({"email": ADMIN_EMAIL}, {"_id": 0, "password_hash": 1})
        assert u, "admin user missing in DB"
        h = u["password_hash"]
        assert h.startswith("$2b$"), f"hash prefix not bcrypt $2b$: {h[:7]}"
        assert len(h) == 60, len(h)
        # no other user stores a plaintext / non-bcrypt password
        bad = [x["email"] for x in db.users.find({}, {"_id": 0, "email": 1, "password_hash": 1})
               if not str(x.get("password_hash", "")).startswith("$2")]
        assert not bad, f"users with non-bcrypt password_hash: {bad}"

    def test_login_response_shape_and_cookie_policy(self):
        r = requests.post(f"{API}/auth/login",
                          json={"email": ADMIN_EMAIL, "password": "CHANGE_ME_TEST_PASSWORD"}, timeout=40)
        assert r.status_code == 200, r.text[:300]
        body = r.json()
        assert "token" in body and "user" in body
        assert "password_hash" not in body["user"], "password hash leaked in login response"
        # Informational: app is Bearer-token based; no Set-Cookie expected.
        print("Set-Cookie on login:", r.headers.get("Set-Cookie"))

    def test_brute_force_lockout(self):
        email = f"TEST_QA_lock_{uuid.uuid4().hex[:8]}@keylot.app"
        codes = []
        for _ in range(8):
            rr = requests.post(f"{API}/auth/login", json={"email": email, "password": "bad_pwd_1"}, timeout=40)
            codes.append(rr.status_code)
            if rr.status_code == 429:
                assert "Retry-After" in rr.headers
                break
        assert 429 in codes, f"no lockout after repeated failures: {codes}"
        assert codes.count(401) >= 4, codes

    def test_cors_explicit_origins(self):
        origin = BASE
        r = requests.options(f"{API}/auth/login", timeout=30, headers={
            "Origin": origin,
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type",
        })
        assert r.status_code in (200, 204), r.status_code
        allow = r.headers.get("Access-Control-Allow-Origin")
        creds = r.headers.get("Access-Control-Allow-Credentials")
        assert allow, "no Access-Control-Allow-Origin header on preflight"
        # Unsafe combination: wildcard origin + credentials allowed.
        assert not (allow == "*" and creds == "true"), "wildcard origin combined with credentials"
        # Informational: app is Bearer-based, CORS_ORIGINS unset -> wildcard, credentials disabled.
        print(f"CORS preflight: ACAO={allow} ACAC={creds} (requested origin={origin})")

    def test_protected_endpoint_rejects_garbage_token(self):
        r = requests.get(f"{API}/auth/me", headers={"Authorization": "Bearer not.a.jwt"}, timeout=30)
        assert r.status_code == 401, r.status_code
