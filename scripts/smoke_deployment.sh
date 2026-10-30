#!/bin/sh
set -eu

: "${APP_URL:?APP_URL is required, for example https://staging.example.com}"
APP_URL=${APP_URL%/}

command -v curl >/dev/null 2>&1 || {
  echo "curl is required" >&2
  exit 1
}

TMP_DIR=$(mktemp -d)
trap 'rm -rf "$TMP_DIR"' EXIT HUP INT TERM

curl --fail --silent --show-error --max-time 10 "$APP_URL/health" > "$TMP_DIR/health.json"
grep -q '"status"[[:space:]]*:[[:space:]]*"ok"' "$TMP_DIR/health.json"

curl --fail --silent --show-error --max-time 10 "$APP_URL/ready" > "$TMP_DIR/ready.json"
grep -q '"status"[[:space:]]*:[[:space:]]*"ready"' "$TMP_DIR/ready.json"

curl --fail --silent --show-error --max-time 10 "$APP_URL/api/version" > "$TMP_DIR/version.json"
grep -q '"version"' "$TMP_DIR/version.json"

curl --fail --silent --show-error --max-time 10 --dump-header "$TMP_DIR/headers.txt" --output "$TMP_DIR/index.html" "$APP_URL/"
grep -qi '^strict-transport-security:' "$TMP_DIR/headers.txt"
grep -qi '^content-security-policy:' "$TMP_DIR/headers.txt"
grep -qi '^x-content-type-options:[[:space:]]*nosniff' "$TMP_DIR/headers.txt"
grep -qi '^x-frame-options:[[:space:]]*DENY' "$TMP_DIR/headers.txt"

DOCS_STATUS=$(curl --silent --output /dev/null --write-out '%{http_code}' --max-time 10 "$APP_URL/openapi.json")
test "$DOCS_STATUS" = "404" || {
  echo "API documentation is unexpectedly exposed (HTTP $DOCS_STATUS)" >&2
  exit 1
}

echo "Deployment smoke checks passed for $APP_URL"
