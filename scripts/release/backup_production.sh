#!/bin/sh
# Sauvegarde complète de la production avant release.
# Ne modifie jamais la base. Ne jamais committer les identifiants.
set -eu
umask 077

: "${PROD_MONGO_URI:?PROD_MONGO_URI requis}"
: "${PROD_DB_NAME:?PROD_DB_NAME requis}"
CONFIRM=${CONFIRM:-}
APP_URL=${APP_URL:-https://kylot-preview.onrender.com}
EXPECTED_COMMIT=${EXPECTED_COMMIT:-79f0f2e}

if [ "$CONFIRM" != "BACKUP" ]; then
  echo "Refus : relance avec CONFIRM=BACKUP après avoir vérifié la cible." >&2
  exit 1
fi

case "$PROD_DB_NAME" in
  *qa*|*QA*)
    echo "Refus : la cible ressemble à QA, pas à la production." >&2
    exit 1
    ;;
esac
if [ -n "${QA_MONGO_URI:-}" ] && [ "$PROD_MONGO_URI" = "$QA_MONGO_URI" ]; then
  echo "Refus : PROD_MONGO_URI est identique à QA_MONGO_URI." >&2
  exit 1
fi

command -v mongodump >/dev/null 2>&1 || { echo "mongodump requis" >&2; exit 1; }

STAMP=$(date -u +%Y%m%dT%H%M%SZ)
OUT="backups/release-${STAMP}"
mkdir -p "$OUT"
chmod 700 "$OUT"

ARCHIVE="$OUT/prod-before-${STAMP}.archive.gz"
echo "1/3 Sauvegarde MongoDB complète..."
mongodump --uri="$PROD_MONGO_URI" --db="$PROD_DB_NAME" --archive="$ARCHIVE" --gzip
chmod 600 "$ARCHIVE"

echo "2/3 Empreinte SHA-256..."
if command -v shasum >/dev/null 2>&1; then
  shasum -a 256 "$ARCHIVE" > "$ARCHIVE.sha256"
else
  sha256sum "$ARCHIVE" > "$ARCHIVE.sha256"
fi

echo "3/3 Métadonnées de release..."
API_VERSION=$(curl -fsS --max-time 15 "$APP_URL/api/version" || echo '{"version":"indisponible"}')
cat > "$OUT/release.json" <<JSON
{
  "created_at": "$STAMP",
  "database": "$PROD_DB_NAME",
  "backup": "$ARCHIVE",
  "expected_commit": "$EXPECTED_COMMIT",
  "api_version_before": $API_VERSION
}
JSON
chmod 600 "$OUT/release.json"

echo "Sauvegarde OK : $ARCHIVE"
echo "Checksum      : $ARCHIVE.sha256"
echo "Métadonnées   : $OUT/release.json"
echo
echo "Restauration de test (JAMAIS sur la production) :"
echo "mongorestore --uri=\"\$TEST_MONGO_URI\" --archive=\"$ARCHIVE\" --gzip --nsFrom=\"$PROD_DB_NAME.*\" --nsTo=\"kylot_restore_test.*\""
