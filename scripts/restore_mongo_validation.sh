#!/bin/sh
set -eu

: "${MONGO_URL:?MONGO_URL is required}"
: "${DB_NAME:?DB_NAME is required}"
: "${RESTORE_TARGET_DB:?RESTORE_TARGET_DB is required}"
: "${BACKUP_ARCHIVE:?BACKUP_ARCHIVE is required}"

if [ "$RESTORE_TARGET_DB" = "$DB_NAME" ]; then
  echo "Refusing to restore over the source database" >&2
  exit 1
fi

if [ "${KYLOT_ALLOW_RESTORE_VALIDATION:-}" != "I_UNDERSTAND_THIS_REPLACES_THE_TARGET_DB" ]; then
  echo "Restore blocked: explicit acknowledgement is missing" >&2
  exit 1
fi

command -v mongorestore >/dev/null 2>&1 || {
  echo "mongorestore is required" >&2
  exit 1
}

test -f "$BACKUP_ARCHIVE" || {
  echo "Backup archive not found" >&2
  exit 1
}

mongorestore \
  --uri="$MONGO_URL" \
  --archive="$BACKUP_ARCHIVE" \
  --gzip \
  --drop \
  --nsFrom="$DB_NAME.*" \
  --nsTo="$RESTORE_TARGET_DB.*"

echo "Restore validation completed into database: $RESTORE_TARGET_DB"
