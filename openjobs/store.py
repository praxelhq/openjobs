"""SQLite storage and search. Only the CLI writes; HTTP and MCP are read-only."""

from __future__ import annotations

import hashlib
import json
import os
import re
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator
from urllib.parse import urlparse

MAX_FEED_BYTES = 50 * 1024 * 1024
MAX_SOURCE_JOBS = 10_000
MAX_DESCRIPTION_CHARS = 100_000
MAX_TOTAL_DESCRIPTION_CHARS = 20_000_000


def db_path() -> Path:
    return Path(os.environ.get("OPENJOBS_DB", "data/jobs.sqlite"))


def connect(path: Path | None = None) -> sqlite3.Connection:
    target = path or db_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(target)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA journal_mode=WAL")
    connection.execute("PRAGMA busy_timeout=5000")
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS jobs (
            id TEXT PRIMARY KEY,
            source TEXT NOT NULL,
            source_id TEXT NOT NULL,
            title TEXT NOT NULL,
            company TEXT NOT NULL,
            location TEXT NOT NULL DEFAULT '',
            work_mode TEXT NOT NULL DEFAULT 'unknown',
            description TEXT NOT NULL DEFAULT '',
            source_url TEXT NOT NULL,
            posted_at TEXT,
            first_seen_at TEXT NOT NULL,
            last_seen_at TEXT NOT NULL,
            active INTEGER NOT NULL DEFAULT 1,
            UNIQUE(source, source_id)
        );
        CREATE INDEX IF NOT EXISTS jobs_filters ON jobs(active, company, work_mode);
        CREATE VIRTUAL TABLE IF NOT EXISTS jobs_fts USING fts5(
            title, company, location, description, content='jobs', content_rowid='rowid'
        );
        CREATE TRIGGER IF NOT EXISTS jobs_ai AFTER INSERT ON jobs BEGIN
            INSERT INTO jobs_fts(rowid, title, company, location, description)
            VALUES (
                new.rowid, new.title, new.company, new.location, new.description
            );
        END;
        CREATE TRIGGER IF NOT EXISTS jobs_ad AFTER DELETE ON jobs BEGIN
            INSERT INTO jobs_fts(jobs_fts, rowid, title, company, location, description)
            VALUES (
                'delete', old.rowid, old.title, old.company,
                old.location, old.description
            );
        END;
        CREATE TRIGGER IF NOT EXISTS jobs_au AFTER UPDATE ON jobs BEGIN
            INSERT INTO jobs_fts(jobs_fts, rowid, title, company, location, description)
            VALUES (
                'delete', old.rowid, old.title, old.company,
                old.location, old.description
            );
            INSERT INTO jobs_fts(rowid, title, company, location, description)
            VALUES (
                new.rowid, new.title, new.company, new.location, new.description
            );
        END;
        CREATE TABLE IF NOT EXISTS source_syncs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source TEXT NOT NULL,
            import_kind TEXT NOT NULL,
            synced_at TEXT,
            snapshot_sha256 TEXT,
            input_count INTEGER,
            active_count INTEGER NOT NULL,
            new_count INTEGER,
            updated_count INTEGER,
            reopened_count INTEGER,
            closed_count INTEGER,
            unchanged_count INTEGER
        );
        CREATE INDEX IF NOT EXISTS source_syncs_history
        ON source_syncs(source, id DESC);
        """
    )
    columns = {row["name"] for row in connection.execute("PRAGMA table_info(jobs)")}
    if "last_seen_at" not in columns and "last_verified_at" in columns:
        connection.execute(
            "ALTER TABLE jobs RENAME COLUMN last_verified_at TO last_seen_at"
        )
        connection.commit()
    # Preview databases predate source receipts. Record only what their current
    # index proves; past feed contents, sync time, and change counts are unknown.
    missing_sources = [
        row[0]
        for row in connection.execute(
            "SELECT source FROM jobs EXCEPT SELECT source FROM source_syncs"
        )
    ]
    if missing_sources:
        with connection:
            for source in missing_sources:
                active_count = connection.execute(
                    "SELECT COUNT(*) FROM jobs WHERE source = ? AND active = 1",
                    (source,),
                ).fetchone()[0]
                connection.execute(
                    """
                    INSERT INTO source_syncs (source, import_kind, active_count)
                    VALUES (?, 'legacy', ?)
                    """,
                    (source, active_count),
                )
    return connection


@contextmanager
def open_db(path: Path | None = None) -> Iterator[sqlite3.Connection]:
    connection = connect(path)
    try:
        yield connection
    finally:
        connection.close()


class IndexUnavailableError(RuntimeError):
    """The read-only job index is missing or not initialized."""


@contextmanager
def read_db(path: Path | None = None) -> Iterator[sqlite3.Connection]:
    """Open an initialized index without creating a database or running DDL."""
    target = (path or db_path()).expanduser().resolve()
    connection: sqlite3.Connection | None = None
    try:
        connection = sqlite3.connect(f"{target.as_uri()}?mode=ro", uri=True)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA busy_timeout=5000")
        connection.execute("PRAGMA query_only=ON")
        connection.execute("SELECT 1 FROM jobs LIMIT 0")
        connection.execute("SELECT 1 FROM source_syncs LIMIT 0")
        connection.execute("BEGIN")  # Keep count and page reads on one snapshot.
    except sqlite3.Error as exc:
        if connection is not None:
            connection.close()
        raise IndexUnavailableError("No initialized job index is available") from exc
    try:
        yield connection
    finally:
        connection.close()


PUBLIC_FIELDS = (
    "id",
    "title",
    "company",
    "location",
    "work_mode",
    "description",
    "source",
    "source_url",
    "posted_at",
    "first_seen_at",
    "last_seen_at",
)
RECEIPT_FIELDS = (
    "id",
    "source",
    "import_kind",
    "synced_at",
    "snapshot_sha256",
    "input_count",
    "active_count",
    "new_count",
    "updated_count",
    "reopened_count",
    "closed_count",
    "unchanged_count",
)
JOB_CONTENT_FIELDS = (
    "title",
    "company",
    "location",
    "work_mode",
    "description",
    "source_url",
    "posted_at",
)


def public_job(row: sqlite3.Row) -> dict[str, Any]:
    return {field: row[field] for field in PUBLIC_FIELDS}


def public_receipt(row: sqlite3.Row) -> dict[str, Any]:
    return {field: row[field] for field in RECEIPT_FIELDS}


def _snapshot_sha256(jobs: list[dict[str, Any]]) -> str:
    """Fingerprint normalized feed content independent of order or derived job IDs."""
    digest = hashlib.sha256()
    digest.update(b"[")
    for index, job in enumerate(sorted(jobs, key=lambda item: item["source_id"])):
        if index:
            digest.update(b",")
        canonical = {key: value for key, value in job.items() if key != "id"}
        digest.update(
            json.dumps(
                canonical, ensure_ascii=True, sort_keys=True, separators=(",", ":")
            ).encode("utf-8")
        )
    digest.update(b"]")
    return digest.hexdigest()


def _validated_job(source: str, raw: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise ValueError("each job must be a JSON object")
    raw_id = raw.get("source_id")
    source_id = (
        str(raw_id).strip()
        if isinstance(raw_id, (str, int)) and not isinstance(raw_id, bool)
        else ""
    )
    title = raw.get("title")
    company = raw.get("company")
    source_url = raw.get("source_url")
    title = title.strip() if isinstance(title, str) else ""
    company = company.strip() if isinstance(company, str) else ""
    source_url = source_url.strip() if isinstance(source_url, str) else ""
    if not all((source_id, title, company, source_url)):
        raise ValueError("each job needs source_id, title, company, and source_url")
    for field, value, maximum in (
        ("source_id", source_id, 200),
        ("title", title, 500),
        ("company", company, 500),
        ("source_url", source_url, 4096),
    ):
        if len(value) > maximum:
            raise ValueError(f"{field} exceeds {maximum} characters")
    url = urlparse(source_url)
    if (
        url.scheme not in {"http", "https"}
        or not url.netloc
        or url.username
        or url.password
    ):
        raise ValueError("source_url must be an absolute HTTP(S) URL")
    work_mode = str(raw.get("work_mode") or "unknown").lower()
    if work_mode not in {"remote", "hybrid", "onsite", "unknown"}:
        raise ValueError("work_mode must be remote, hybrid, onsite, or unknown")
    posted_at = raw.get("posted_at")
    if posted_at is not None:
        try:
            datetime.fromisoformat(str(posted_at).replace("Z", "+00:00"))
        except ValueError as exc:
            raise ValueError("posted_at must be ISO 8601 or null") from exc
        posted_at = str(posted_at)
    location = str(raw.get("location") or "").strip()
    description = str(raw.get("description") or "").strip()
    if len(location) > 500:
        raise ValueError("location exceeds 500 characters")
    if len(description) > MAX_DESCRIPTION_CHARS:
        raise ValueError(f"description exceeds {MAX_DESCRIPTION_CHARS} characters")
    identity = json.dumps([source, source_id], ensure_ascii=True, separators=(",", ":"))
    return {
        "id": "job_" + hashlib.sha256(identity.encode()).hexdigest()[:20],
        "source": source,
        "source_id": source_id,
        "title": title,
        "company": company,
        "location": location,
        "work_mode": work_mode,
        "description": description,
        "source_url": source_url,
        "posted_at": posted_at,
    }


def sync_jobs_with_receipt(
    connection: sqlite3.Connection,
    source: str,
    raw_jobs: list[dict[str, Any]],
    *,
    import_kind: str = "json",
    allow_empty: bool = False,
) -> dict[str, Any]:
    """Replace one complete source snapshot and record observed changes atomically."""
    if not re.fullmatch(r"[a-zA-Z0-9:_-]{1,100}", source):
        raise ValueError(
            "source must contain only letters, numbers, colon, dash, underscore"
        )
    if import_kind not in {"json", "greenhouse"}:
        raise ValueError("import_kind must be json or greenhouse")
    if not isinstance(raw_jobs, list):
        raise ValueError("feed must be an array of jobs")
    if len(raw_jobs) > MAX_SOURCE_JOBS:
        raise ValueError(f"feed exceeds {MAX_SOURCE_JOBS} jobs")
    jobs = []
    total_description_chars = 0
    for raw in raw_jobs:
        job = _validated_job(source, raw)
        total_description_chars += len(job["description"])
        if total_description_chars > MAX_TOTAL_DESCRIPTION_CHARS:
            raise ValueError(
                f"feed descriptions exceed {MAX_TOTAL_DESCRIPTION_CHARS} characters"
            )
        jobs.append(job)
    ids = [job["source_id"] for job in jobs]
    if len(ids) != len(set(ids)):
        raise ValueError("duplicate source_id in feed")
    if not jobs and not allow_empty:
        raise ValueError(
            "empty feed would close every job; pass allow_empty=True to confirm"
        )
    timestamp = datetime.now(timezone.utc).isoformat(timespec="microseconds")
    snapshot_sha256 = _snapshot_sha256(jobs)

    # A caller may already be inside a larger SQLite transaction. A savepoint
    # keeps this operation atomic without committing unrelated caller writes.
    nested = connection.in_transaction
    connection.execute("SAVEPOINT openjobs_sync" if nested else "BEGIN IMMEDIATE")
    try:
        previous = {
            row["source_id"]: row
            for row in connection.execute(
                "SELECT * FROM jobs WHERE source = ?",
                (source,),
            )
        }
        incoming = set(ids)
        counts = {
            "new_count": 0,
            "updated_count": 0,
            "reopened_count": 0,
            "closed_count": sum(
                row["active"] == 1 and key not in incoming
                for key, row in previous.items()
            ),
            "unchanged_count": 0,
        }
        for job in jobs:
            old = previous.get(job["source_id"])
            if old is None:
                counts["new_count"] += 1
            elif not old["active"]:
                counts["reopened_count"] += 1
            elif any(old[field] != job[field] for field in JOB_CONTENT_FIELDS):
                counts["updated_count"] += 1
            else:
                counts["unchanged_count"] += 1

        connection.execute("UPDATE jobs SET active = 0 WHERE source = ?", (source,))
        for job in jobs:
            connection.execute(
                """
                INSERT INTO jobs (
                    id, source, source_id, title, company, location, work_mode,
                    description, source_url, posted_at,
                    first_seen_at, last_seen_at, active
                ) VALUES (
                    :id, :source, :source_id, :title, :company, :location, :work_mode,
                    :description, :source_url, :posted_at, :seen_at, :seen_at, 1
                ) ON CONFLICT(source, source_id) DO UPDATE SET
                    title=excluded.title, company=excluded.company,
                    location=excluded.location, work_mode=excluded.work_mode,
                    description=excluded.description, source_url=excluded.source_url,
                    posted_at=excluded.posted_at, last_seen_at=excluded.last_seen_at,
                    active=1
                """,
                {**job, "seen_at": timestamp},
            )
        cursor = connection.execute(
            """
            INSERT INTO source_syncs (
                source, import_kind, synced_at, snapshot_sha256, input_count,
                active_count, new_count, updated_count, reopened_count,
                closed_count, unchanged_count
            ) VALUES (
                :source, :import_kind, :synced_at, :snapshot_sha256, :input_count,
                :active_count, :new_count, :updated_count, :reopened_count,
                :closed_count, :unchanged_count
            )
            """,
            {
                "source": source,
                "import_kind": import_kind,
                "synced_at": timestamp,
                "snapshot_sha256": snapshot_sha256,
                "input_count": len(jobs),
                "active_count": len(jobs),
                **counts,
            },
        )
        receipt = public_receipt(
            connection.execute(
                "SELECT * FROM source_syncs WHERE id = ?",
                (cursor.lastrowid,),
            ).fetchone()
        )
    except Exception:
        if nested:
            connection.execute("ROLLBACK TO SAVEPOINT openjobs_sync")
            connection.execute("RELEASE SAVEPOINT openjobs_sync")
        else:
            connection.rollback()
        raise
    else:
        if nested:
            connection.execute("RELEASE SAVEPOINT openjobs_sync")
        else:
            connection.commit()
    return receipt


def sync_jobs(
    connection: sqlite3.Connection,
    source: str,
    raw_jobs: list[dict[str, Any]],
    *,
    allow_empty: bool = True,
) -> int:
    """Compatibility wrapper returning the latest active count for a source."""
    return sync_jobs_with_receipt(
        connection, source, raw_jobs, allow_empty=allow_empty
    )["active_count"]


def list_sources(
    connection: sqlite3.Connection, *, limit: int = 20, offset: int = 0
) -> dict[str, Any]:
    """List the latest successful import receipt for each source."""
    _validate_page(limit, offset)
    total = connection.execute(
        "SELECT COUNT(DISTINCT source) FROM source_syncs"
    ).fetchone()[0]
    rows = connection.execute(
        """
        SELECT receipt.* FROM source_syncs AS receipt
        JOIN (SELECT source, MAX(id) AS id FROM source_syncs GROUP BY source) AS latest
          ON latest.id = receipt.id
        ORDER BY receipt.source COLLATE NOCASE, receipt.source
        LIMIT ? OFFSET ?
        """,
        (limit, offset),
    ).fetchall()
    return {
        "sources": [public_receipt(row) for row in rows],
        "total": total,
        "limit": limit,
        "offset": offset,
    }


def get_source(connection: sqlite3.Connection, source: str) -> dict[str, Any] | None:
    row = connection.execute(
        "SELECT * FROM source_syncs WHERE source = ? ORDER BY id DESC LIMIT 1",
        (source,),
    ).fetchone()
    return public_receipt(row) if row else None


def get_source_syncs(
    connection: sqlite3.Connection,
    source: str,
    *,
    limit: int = 20,
    offset: int = 0,
) -> dict[str, Any] | None:
    _validate_page(limit, offset)
    if get_source(connection, source) is None:
        return None
    total = connection.execute(
        "SELECT COUNT(*) FROM source_syncs WHERE source = ?",
        (source,),
    ).fetchone()[0]
    rows = connection.execute(
        "SELECT * FROM source_syncs WHERE source = ? ORDER BY id DESC LIMIT ? OFFSET ?",
        (source, limit, offset),
    ).fetchall()
    return {
        "source": source,
        "syncs": [public_receipt(row) for row in rows],
        "total": total,
        "limit": limit,
        "offset": offset,
    }


def _validate_page(limit: int, offset: int) -> None:
    if not 1 <= limit <= 100 or offset < 0:
        raise ValueError("limit must be 1–100 and offset must be nonnegative")


def search_jobs(
    connection: sqlite3.Connection,
    *,
    query: str = "",
    location: str = "",
    company: str = "",
    company_exact: bool = False,
    work_mode: str = "",
    limit: int = 20,
    offset: int = 0,
) -> dict[str, Any]:
    if work_mode and work_mode not in {"remote", "hybrid", "onsite", "unknown"}:
        raise ValueError("invalid work_mode")
    _validate_page(limit, offset)
    terms = re.findall(r"\w+", query, re.UNICODE)
    if len(terms) > 12 or len(query) > 200:
        raise ValueError("query is too long")
    where = ["jobs.active = 1"]
    params: list[Any] = []
    join = ""
    if terms:
        join = "JOIN jobs_fts ON jobs_fts.rowid = jobs.rowid"
        where.append("jobs_fts MATCH ?")
        params.append(
            " AND ".join('"' + term.replace('"', '""') + '"' for term in terms)
        )
    for column, value in (
        ("location", location),
        ("company", company if not company_exact else ""),
    ):
        if value:
            where.append(f"jobs.{column} LIKE ? ESCAPE '\\'")
            escaped = (
                value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
            )
            params.append(f"%{escaped}%")
    if company_exact:
        where.append("jobs.company = ? COLLATE NOCASE")
        params.append(company)
    if work_mode:
        where.append("jobs.work_mode = ?")
        params.append(work_mode)
    clause = f"FROM jobs {join} WHERE " + " AND ".join(where)
    total = connection.execute(f"SELECT COUNT(*) {clause}", params).fetchone()[0]
    order = (
        "bm25(jobs_fts), jobs.last_seen_at DESC"
        if terms
        else "jobs.last_seen_at DESC, jobs.id"
    )
    rows = connection.execute(
        f"SELECT jobs.* {clause} ORDER BY {order} LIMIT ? OFFSET ?",
        [*params, limit, offset],
    ).fetchall()
    return {
        "jobs": [public_job(row) for row in rows],
        "total": total,
        "limit": limit,
        "offset": offset,
    }


def get_job(connection: sqlite3.Connection, job_id: str) -> dict[str, Any] | None:
    row = connection.execute(
        "SELECT * FROM jobs WHERE id = ? AND active = 1", (job_id,)
    ).fetchone()
    return public_job(row) if row else None
