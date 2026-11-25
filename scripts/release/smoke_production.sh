#!/bin/sh
# Smoke test production en lecture seule. Aucune authentification, aucune écriture.
set -eu
APP_URL=${APP_URL:-https://kylot-preview.onrender.com}
APP_URL=${APP_URL%/}
EXPECTED_VERSION=${EXPECTED_VERSION:-79f0f2e}
TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT HUP INT TERM

command -v curl >/dev/null 2>&1 || { echo "curl requis" >&2; exit 1; }

echo "1/6 Health..."
curl -fsS --max-time 15 "$APP_URL/health" > "$TMP/health.json"
grep -q '"status"[[:space:]]*:[[:space:]]*"ok"' "$TMP/health.json"

echo "2/6 Readiness..."
curl -fsS --max-time 15 "$APP_URL/ready" > "$TMP/ready.json"
grep -q '"status"[[:space:]]*:[[:space:]]*"ready"' "$TMP/ready.json"

echo "3/6 Version..."
curl -fsS --max-time 15 "$APP_URL/api/version" > "$TMP/version.json"
grep -q '"version"' "$TMP/version.json"
if [ -n "$EXPECTED_VERSION" ]; then
  grep -q "$EXPECTED_VERSION" "$TMP/version.json" || {
    echo "Version attendue absente : $EXPECTED_VERSION" >&2
    cat "$TMP/version.json" >&2
    exit 1
  }
fi

echo "4/6 En-têtes de sécurité..."
curl -fsS --max-time 15 -D "$TMP/headers.txt" -o "$TMP/index.html" "$APP_URL/"
grep -qi '^strict-transport-security:' "$TMP/headers.txt"
grep -qi '^content-security-policy:' "$TMP/headers.txt"
grep -qi '^x-content-type-options:[[:space:]]*nosniff' "$TMP/headers.txt"
grep -qi '^x-frame-options:[[:space:]]*DENY' "$TMP/headers.txt"

echo "5/6 Documentation API fermée..."
STATUS=$(curl -sS -o /dev/null -w '%{http_code}' --max-time 15 "$APP_URL/openapi.json")
[ "$STATUS" = "404" ] || { echo "OpenAPI exposé : HTTP $STATUS" >&2; exit 1; }

echo "6/6 Build frontend..."
curl -fsS --max-time 15 "$APP_URL/asset-manifest.json" > "$TMP/manifest.json"
grep -q 'main.js' "$TMP/manifest.json"

echo "Smoke production OK : $APP_URL"
