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

TMP_DIR=""
cleanup() {
  if [ -n "$TMP_DIR" ] && [ -d "$TMP_DIR" ]; then
    rm -rf "$TMP_DIR"
  fi
}
trap cleanup EXIT HUP INT TERM

# A backup can be either a real mongodump archive or the operational
# tar.gz produced by scripts/backup_mongo.sh (directories of BSON files).
if tar -tzf "$BACKUP_ARCHIVE" >/dev/null 2>&1; then
  TMP_DIR=$(mktemp -d "${TMPDIR:-/tmp}/kylot-restore.XXXXXX")
  tar -xzf "$BACKUP_ARCHIVE" -C "$TMP_DIR"
  SRC_DIR=$(find "$TMP_DIR" -type d -name "$DB_NAME" -print -quit)
  if [ -z "$SRC_DIR" ]; then
    echo "Database directory '$DB_NAME' not found inside $BACKUP_ARCHIVE" >&2
    exit 1
  fi
  mongorestore \
    --uri="$MONGO_URL" \
    --dir="$SRC_DIR" \
    --drop \
    --numInsertionWorkersPerCollection=4 \
    --nsFrom="$DB_NAME.*" \
    --nsTo="$RESTORE_TARGET_DB.*"
else
  mongorestore \
    --uri="$MONGO_URL" \
    --archive="$BACKUP_ARCHIVE" \
    --gzip \
    --drop \
    --numInsertionWorkersPerCollection=4 \
    --nsFrom="$DB_NAME.*" \
    --nsTo="$RESTORE_TARGET_DB.*"
fi

echo "Restore validation completed into database: $RESTORE_TARGET_DB"
