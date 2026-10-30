#!/bin/sh
set -eu

: "${MONGO_URL:?MONGO_URL is required}"
: "${DB_NAME:?DB_NAME is required}"

command -v mongodump >/dev/null 2>&1 || {
  echo "mongodump is required" >&2
  exit 1
}

BACKUP_DIR=${BACKUP_DIR:-./backups}
STAMP=$(date -u +%Y%m%dT%H%M%SZ)
ARCHIVE="$BACKUP_DIR/kylot-${DB_NAME}-${STAMP}.archive.gz"

mkdir -p "$BACKUP_DIR"
umask 077
mongodump --uri="$MONGO_URL" --db="$DB_NAME" --archive="$ARCHIVE" --gzip

if command -v shasum >/dev/null 2>&1; then
  shasum -a 256 "$ARCHIVE" > "$ARCHIVE.sha256"
elif command -v sha256sum >/dev/null 2>&1; then
  sha256sum "$ARCHIVE" > "$ARCHIVE.sha256"
else
  echo "No SHA-256 utility found; backup created without checksum" >&2
fi

echo "Backup created: $ARCHIVE"
