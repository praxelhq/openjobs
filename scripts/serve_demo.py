"""Seed and serve the stage demo, with only the repository's fictional jobs."""

from __future__ import annotations

import json
import os
import sqlite3
from pathlib import Path
from urllib.parse import urlparse

from openjobs.store import (
    _snapshot_sha256,
    _validated_job,
    open_db,
    sync_jobs_with_receipt,
)

DATA_DIR = Path("/app/data")
DB = DATA_DIR / "jobs.sqlite"
FEED = Path("/app/examples/demo.json")
SOURCE = "demo:fictional"
APP_UID = 10001
APP_GID = 10001


def fail(message: str) -> None:
    raise SystemExit(f"Demo startup refused: {message}")


def prepare_storage() -> None:
    if os.environ.get("OPENJOBS_DEMO_MODE") != "fictional":
        fail("set OPENJOBS_DEMO_MODE=fictional explicitly")
    if os.environ.get("OPENJOBS_DB") != str(DB):
        fail(f"OPENJOBS_DB must be {DB}")
    if os.environ.get("RAILWAY_PROJECT_ID") and os.environ.get(
        "RAILWAY_VOLUME_MOUNT_PATH"
    ) != str(DATA_DIR):
        fail("attach a Railway volume at /app/data")
    if DATA_DIR.is_symlink() or DB.is_symlink():
        fail("data directory and database must not be symlinks")
    if not DATA_DIR.is_mount():
        fail("attach a persistent volume at /app/data")

    if os.geteuid() == 0:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        paths = (
            DATA_DIR,
            DB,
            DB.with_name("jobs.sqlite-wal"),
            DB.with_name("jobs.sqlite-shm"),
        )
        for path in paths:
            if path.is_symlink():
                fail("SQLite storage must not contain symlinks")
            if path.exists():
                os.chown(path, APP_UID, APP_GID)
        os.setgroups([])
        os.setgid(APP_GID)
        os.setuid(APP_UID)
    if (os.geteuid(), os.getegid()) != (APP_UID, APP_GID):
        fail("the server must run as UID/GID 10001")
    if not os.access(DATA_DIR, os.W_OK):
        fail("/app/data is not writable by the non-root server")


def seed() -> None:
    payload = json.loads(FEED.read_text(encoding="utf-8"))
    if not isinstance(payload, list) or not payload:
        fail("fictional fixture is missing or empty")
    for row in payload:
        if not isinstance(row, dict):
            fail("fictional fixture must contain job objects")
        company = row.get("company")
        url = row.get("source_url")
        if (
            not isinstance(company, str)
            or not company.endswith(" (demo)")
            or not isinstance(url, str)
            or urlparse(url).hostname != "example.com"
            or row.get("posted_at") is not None
        ):
            fail("fictional jobs need demo company names and example.com links")
    fixture_ids = {row["source_id"] for row in payload}
    if len(fixture_ids) != len(payload):
        fail("fictional fixture contains duplicate IDs")

    fixture_by_id = {row["source_id"]: row for row in payload}
    expected_digest = _snapshot_sha256([_validated_job(SOURCE, row) for row in payload])
    content_fields = (
        "title",
        "company",
        "location",
        "work_mode",
        "description",
        "source_url",
        "posted_at",
    )
    with open_db(DB) as connection:
        known_sources = {
            row[0]
            for row in connection.execute(
                "SELECT source FROM jobs UNION SELECT source FROM source_syncs"
            )
        }
        stored_ids = {
            row[0] for row in connection.execute("SELECT source_id FROM jobs")
        }
        if known_sources - {SOURCE} or stored_ids - fixture_ids:
            fail("database contains data outside the fictional fixture")
        if any(
            row[0] != expected_digest
            for row in connection.execute("SELECT snapshot_sha256 FROM source_syncs")
        ):
            fail("receipt history does not match the fictional fixture")
        for row in connection.execute("SELECT * FROM jobs"):
            fixture = fixture_by_id[row["source_id"]]
            if any(row[field] != fixture[field] for field in content_fields):
                fail("stored jobs differ from the fictional fixture")
        receipt = sync_jobs_with_receipt(connection, SOURCE, payload)
    print(
        f"Fictional demo ready: {receipt['active_count']} sample jobs; "
        f"source={SOURCE}; sync={receipt['id']}",
        flush=True,
    )


def main() -> None:
    try:
        prepare_storage()
        seed()
    except (OSError, sqlite3.Error, ValueError, KeyError, TypeError) as exc:
        fail(str(exc))
    port = os.environ.get("PORT", "8000")
    if not port.isdecimal() or not 1 <= int(port) <= 65535:
        fail("PORT must be a TCP port number")
    os.execvp(
        "uvicorn",
        ["uvicorn", "openjobs.api:app", "--host", "0.0.0.0", "--port", port],
    )


if __name__ == "__main__":
    main()
