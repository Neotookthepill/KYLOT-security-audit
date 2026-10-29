"""Explicit, auditable data migration entry point for KYLOT deployments."""

from __future__ import annotations

import argparse
import asyncio
from datetime import datetime, timezone

from pymongo.errors import DuplicateKeyError

from backend import server


MIGRATION_ID = "ship-readiness-2026-10"


async def run_migrations(force: bool = False) -> int:
    existing = await server.db.migration_runs.find_one({"_id": MIGRATION_ID}, {"status": 1})
    if existing and existing.get("status") == "completed" and not force:
        print(f"Migration {MIGRATION_ID} already completed; nothing to do.")
        return 0
    if existing and existing.get("status") == "running":
        print(f"Migration {MIGRATION_ID} is already running; refusing concurrent execution.")
        return 2

    run_record = {
        "_id": MIGRATION_ID,
        "status": "running",
        "started_at": datetime.now(timezone.utc),
        "forced": bool(force),
    }
    if existing:
        claimed = await server.db.migration_runs.update_one(
            {"_id": MIGRATION_ID, "status": {"$ne": "running"}},
            {"$set": {key: value for key, value in run_record.items() if key != "_id"}},
        )
        if claimed.modified_count != 1:
            print(f"Migration {MIGRATION_ID} could not be claimed safely.")
            return 2
    else:
        try:
            await server.db.migration_runs.insert_one(run_record)
        except DuplicateKeyError:
            print(f"Migration {MIGRATION_ID} was claimed by another process.")
            return 2
    try:
        await server.seed_default_company()
        await server.migrate_sales_statuses()
        await server.migrate_projects_assigned_to()
        await server.migrate_multi_tenant()
        report = await server._reconcile_sales_commercials()
        await server._reconcile_cancelled_projects()
        await server.db.migration_runs.update_one(
            {"_id": MIGRATION_ID},
            {"$set": {
                "status": "completed",
                "completed_at": datetime.now(timezone.utc),
                "reconciliation": report,
            }},
        )
    except Exception as exc:
        await server.db.migration_runs.update_one(
            {"_id": MIGRATION_ID},
            {"$set": {
                "status": "failed",
                "failed_at": datetime.now(timezone.utc),
                "error_type": type(exc).__name__,
            }},
        )
        raise

    print(f"Migration {MIGRATION_ID} completed successfully.")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run KYLOT data migrations explicitly")
    parser.add_argument("--apply", action="store_true", help="Required confirmation before changing data")
    parser.add_argument("--force", action="store_true", help="Re-run an already completed idempotent migration")
    args = parser.parse_args(argv)
    if not args.apply:
        parser.error("--apply is required; back up MongoDB before running migrations")
    try:
        return asyncio.run(run_migrations(force=args.force))
    finally:
        server.client.close()


if __name__ == "__main__":
    raise SystemExit(main())
