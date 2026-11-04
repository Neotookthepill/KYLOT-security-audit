#!/usr/bin/env python3
"""Smoke test a deployed staging URL. Never prints cookies, tokens or passwords.

Required:
  STAGING_URL=https://staging.example.com
  STAGING_EMAIL=admin@example.com
  STAGING_PASSWORD=...
Optional:
  STAGING_MFA_CODE=123456       # if the admin has MFA enabled
  STAGING_EXPECTED_VERSION=...  # exact git SHA / APP_VERSION
  STAGING_INSECURE=1            # ignore self-signed TLS (local only)
"""

import http.cookiejar
import json
import os
import ssl
import sys
import urllib.error
import urllib.request


BASE = (os.environ.get("STAGING_URL") or "").rstrip("/")
EMAIL = os.environ.get("STAGING_EMAIL") or ""
PASSWORD = os.environ.get("STAGING_PASSWORD") or ""
MFA_CODE = (os.environ.get("STAGING_MFA_CODE") or "").strip()
EXPECTED = (os.environ.get("STAGING_EXPECTED_VERSION") or "").strip()
INSECURE = (os.environ.get("STAGING_INSECURE") or "").strip() in ("1", "true", "yes")

if not BASE or not EMAIL or not PASSWORD:
    print("STAGING_URL, STAGING_EMAIL and STAGING_PASSWORD are required", file=sys.stderr)
    sys.exit(2)

jar = http.cookiejar.CookieJar()
context = ssl._create_unverified_context() if INSECURE else None
opener = urllib.request.build_opener(
    urllib.request.HTTPCookieProcessor(jar),
    *([urllib.request.HTTPSHandler(context=context)] if context else []),
)
failures = []


def request(method, path, body=None):
    data = None
    headers = {"Accept": "application/json"}
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(f"{BASE}{path}", data=data, headers=headers, method=method)
    try:
        with opener.open(req, timeout=20) as response:
            raw = response.read().decode("utf-8", "replace")
            try:
                payload = json.loads(raw) if raw else None
            except json.JSONDecodeError:
                payload = raw
            return response.status, payload, response.headers
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", "replace")
        try:
            payload = json.loads(raw) if raw else None
        except json.JSONDecodeError:
            payload = raw
        return exc.code, payload, exc.headers


def check(label, condition, detail=""):
    if condition:
        print(f"OK   {label}")
    else:
        print(f"FAIL {label} {detail}".rstrip())
        failures.append(label)


status, health, _ = request("GET", "/health")
check("health", status == 200 and isinstance(health, dict) and health.get("status") == "ok", f"HTTP {status}")

status, ready, _ = request("GET", "/ready")
check("ready (MongoDB)", status == 200 and isinstance(ready, dict) and ready.get("status") == "ready", f"HTTP {status}")

status, version, _ = request("GET", "/api/version")
version_value = version.get("version") if isinstance(version, dict) else None
check("version endpoint", status == 200 and bool(version_value), f"HTTP {status}")
if EXPECTED:
    check("deployed version matches", version_value == EXPECTED, f"expected {EXPECTED}, got {version_value}")

status, login, _ = request("POST", "/api/auth/login", {"email": EMAIL, "password": PASSWORD})
if status == 200 and isinstance(login, dict) and login.get("mfa_required"):
    if not MFA_CODE:
        check("MFA challenge answered", False, "STAGING_MFA_CODE missing")
    else:
        status, login, _ = request("POST", "/api/auth/mfa/verify", {"challenge": login.get("challenge"), "code": MFA_CODE})
check("login", status == 200 and isinstance(login, dict) and login.get("user"), f"HTTP {status}")

status, me, _ = request("GET", "/api/auth/me")
check("session /auth/me", status == 200 and isinstance(me, dict) and me.get("email") == EMAIL.lower(), f"HTTP {status}")

status, clients, _ = request("GET", "/api/clients?limit=1")
check("clients page", status == 200 and isinstance(clients, list), f"HTTP {status}")

status, sales, _ = request("GET", "/api/sales?limit=1")
check("sales page", status == 200 and isinstance(sales, list), f"HTTP {status}")

status, challenges, _ = request("GET", "/api/challenges/current")
check("challenge endpoint", status == 200 and isinstance(challenges, dict) and "challenge" in challenges, f"HTTP {status}")

status, prospection, _ = request("GET", "/api/prospection")
check("prospection endpoint", status == 200 and isinstance(prospection, list), f"HTTP {status}")

status, audit, _ = request("GET", "/api/audit?limit=1")
check("audit page", status == 200 and isinstance(audit, list), f"HTTP {status}")

if failures:
    print(f"\n{len(failures)} smoke check(s) failed: {', '.join(failures)}", file=sys.stderr)
    sys.exit(1)
print("\nStaging smoke test: OK")
