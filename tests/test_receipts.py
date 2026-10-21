import hashlib
import json
import sqlite3
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from openjobs import cli, store
from openjobs.api import create_app
from openjobs.cli import main
from openjobs.store import (
    connect,
    get_job,
    get_source,
    get_source_syncs,
    list_sources,
    read_db,
    search_jobs,
    sync_jobs,
    sync_jobs_with_receipt,
)

DEMO = json.loads((Path(__file__).parent.parent / "examples/demo.json").read_text())


@pytest.fixture
def database(tmp_path):
    connection = connect(tmp_path / "jobs.sqlite")
    yield connection
    connection.close()


def test_receipts_classify_snapshot_changes_and_reappearances(database):
    first = sync_jobs_with_receipt(database, "demo", DEMO)
    assert first["import_kind"] == "json"
    assert first["input_count"] == first["active_count"] == len(DEMO)
    assert {
        key: first[key]
        for key in (
            "new_count",
            "updated_count",
            "reopened_count",
            "closed_count",
            "unchanged_count",
        )
    } == {
        "new_count": len(DEMO),
        "updated_count": 0,
        "reopened_count": 0,
        "closed_count": 0,
        "unchanged_count": 0,
    }
    assert len(first["snapshot_sha256"]) == 64
    original = search_jobs(database)["jobs"][0]

    identical = sync_jobs_with_receipt(database, "demo", list(reversed(DEMO)))
    assert identical["snapshot_sha256"] == first["snapshot_sha256"]
    assert identical["id"] > first["id"]
    assert (
        identical["new_count"]
        == identical["updated_count"]
        == identical["closed_count"]
        == 0
    )
    assert identical["unchanged_count"] == len(DEMO)
    assert (
        get_job(database, original["id"])["first_seen_at"] == original["first_seen_at"]
    )

    changed = {**DEMO[0], "title": "Senior Backend Engineer"}
    new = {**DEMO[0], "source_id": "new-role", "title": "New Engineer"}
    mixed = [changed, *DEMO[1:-1], new]
    third = sync_jobs_with_receipt(database, "demo", mixed)
    assert {
        key: third[key]
        for key in (
            "new_count",
            "updated_count",
            "reopened_count",
            "closed_count",
            "unchanged_count",
        )
    } == {
        "new_count": 1,
        "updated_count": 1,
        "reopened_count": 0,
        "closed_count": 1,
        "unchanged_count": len(DEMO) - 2,
    }
    removed_id = next(
        job["id"]
        for job in database.execute(
            "SELECT id FROM jobs WHERE source_id = ?",
            (DEMO[-1]["source_id"],),
        )
    )
    assert get_job(database, removed_id) is None

    returned = sync_jobs_with_receipt(database, "demo", [*mixed, DEMO[-1]])
    assert returned["reopened_count"] == 1
    assert (
        returned["new_count"]
        == returned["updated_count"]
        == returned["closed_count"]
        == 0
    )
    assert get_job(database, removed_id) is not None
    assert get_source(database, "demo") == returned
    assert get_source_syncs(database, "demo", limit=2)["syncs"] == [returned, third]


def test_receipts_are_source_scoped_and_empty_feed_requires_confirmation(database):
    sync_jobs_with_receipt(database, "demo", DEMO)
    other = sync_jobs_with_receipt(
        database, "partner", [{**DEMO[0], "source_id": "partner-1"}]
    )
    assert list_sources(database, limit=1)["total"] == 2
    assert (
        list_sources(database, limit=1, offset=1)["sources"][0]["source"] == "partner"
    )

    with pytest.raises(ValueError, match="empty feed"):
        sync_jobs_with_receipt(database, "demo", [])
    assert get_source_syncs(database, "demo")["total"] == 1
    assert search_jobs(database)["total"] == len(DEMO) + 1

    emptied = sync_jobs_with_receipt(database, "demo", [], allow_empty=True)
    assert emptied["input_count"] == emptied["active_count"] == 0
    assert emptied["closed_count"] == len(DEMO)
    assert search_jobs(database)["total"] == 1
    assert get_source(database, "partner") == other


def test_invalid_input_and_sql_failure_leave_jobs_and_receipts_intact(database):
    first = sync_jobs_with_receipt(database, "demo", DEMO)
    with pytest.raises(ValueError, match="duplicate"):
        sync_jobs_with_receipt(database, "demo", [DEMO[0], DEMO[0]])
    with pytest.raises(ValueError, match="source_url"):
        sync_jobs_with_receipt(
            database, "demo", [{**DEMO[0], "source_url": "file:///tmp/job"}]
        )
    with pytest.raises(ValueError, match="JSON object"):
        sync_jobs_with_receipt(database, "demo", [None])
    assert get_source_syncs(database, "demo")["total"] == 1

    database.execute("""
        CREATE TRIGGER fail_new_job BEFORE INSERT ON jobs
        WHEN new.source_id = 'boom' BEGIN SELECT RAISE(ABORT, 'injected failure'); END
    """)
    with pytest.raises(sqlite3.IntegrityError, match="injected failure"):
        sync_jobs_with_receipt(
            database,
            "demo",
            [
                {**DEMO[0], "title": "Changed before error"},
                {**DEMO[1], "source_id": "boom"},
            ],
        )
    assert search_jobs(database)["total"] == len(DEMO)
    assert search_jobs(database, query="Changed before error")["total"] == 0
    assert get_source(database, "demo") == first


def test_receipt_respects_callers_outer_transaction(database):
    database.execute("BEGIN")
    sync_jobs_with_receipt(database, "demo", DEMO)
    assert get_source(database, "demo") is not None
    database.rollback()
    assert get_source(database, "demo") is None
    assert search_jobs(database)["total"] == 0


def test_source_api_lists_latest_and_paginates_history(tmp_path):
    path = tmp_path / "jobs.sqlite"
    with connect(path) as connection:
        first = sync_jobs_with_receipt(connection, "demo", DEMO)
        second = sync_jobs_with_receipt(connection, "demo", DEMO)
    client = TestClient(create_app(path))

    assert client.get("/ready").json() == {
        "status": "ready",
        "sources": 1,
        "indexed_jobs": len(DEMO),
    }

    listing = client.get("/v1/sources").json()
    assert listing["total"] == 1
    assert listing["sources"] == [second]
    assert client.get("/v1/sources/demo").json() == second
    history = client.get(
        "/v1/sources/demo/syncs", params={"limit": 1, "offset": 1}
    ).json()
    assert history["total"] == 2
    assert history["syncs"] == [first]
    assert client.get("/v1/sources/missing").status_code == 404
    assert client.get("/v1/sources/missing/syncs").status_code == 404
    assert client.get("/v1/sources", params={"limit": 0}).status_code == 422


def test_ready_requires_a_successful_nonempty_snapshot(tmp_path):
    path = tmp_path / "jobs.sqlite"
    client = TestClient(create_app(path))
    assert client.get("/health").status_code == 200
    assert client.get("/ready").status_code == 503
    assert client.get("/v1/jobs").status_code == 503
    assert not path.exists()
    connection = connect(path)
    connection.close()
    assert client.get("/ready").json() == {
        "status": "ready",
        "sources": 0,
        "indexed_jobs": 0,
    }
    with connect(path) as connection:
        sync_jobs_with_receipt(connection, "demo", DEMO[:1])
    assert client.get("/ready").status_code == 200
    with read_db(path) as connection:
        assert connection.execute("PRAGMA query_only").fetchone()[0] == 1
        with pytest.raises(sqlite3.OperationalError, match="readonly"):
            connection.execute("DELETE FROM jobs")
    with connect(path) as connection:
        sync_jobs_with_receipt(connection, "demo", [], allow_empty=True)
    assert client.get("/ready").json() == {
        "status": "ready",
        "sources": 1,
        "indexed_jobs": 0,
    }


def test_stable_ids_distinguish_colon_pairs_and_preserve_legacy_ids(database):
    left = {**DEMO[0], "source_id": "b:c"}
    right = {**DEMO[0], "source_id": "c"}
    sync_jobs_with_receipt(database, "a", [left])
    sync_jobs_with_receipt(database, "a:b", [right])
    rows = database.execute(
        "SELECT source, source_id, id FROM jobs ORDER BY source"
    ).fetchall()
    assert [(row["source"], row["source_id"]) for row in rows] == [
        ("a", "b:c"),
        ("a:b", "c"),
    ]
    assert rows[0]["id"] != rows[1]["id"]

    legacy_id = "job_" + hashlib.sha256("a:b:c".encode()).hexdigest()[:20]
    database.execute("UPDATE jobs SET id = ? WHERE source = 'a'", (legacy_id,))
    database.commit()
    sync_jobs_with_receipt(database, "a", [left])
    actual_id = database.execute("SELECT id FROM jobs WHERE source = 'a'").fetchone()[0]
    assert actual_id == legacy_id
    assert search_jobs(database)["total"] == 2


def test_legacy_empty_sync_wrapper_retains_close_all_behavior(database):
    sync_jobs(database, "demo", DEMO[:1])
    assert sync_jobs(database, "demo", []) == 0
    assert search_jobs(database)["total"] == 0


def test_existing_database_backfills_all_sources_without_inventing_history(tmp_path):
    path = tmp_path / "jobs.sqlite"
    with connect(path) as connection:
        sync_jobs(connection, "first", DEMO[:1])
        sync_jobs(connection, "second", DEMO[1:2])
    with sqlite3.connect(path) as connection:
        connection.execute("DROP TABLE source_syncs")

    with connect(path) as connection:
        listing = list_sources(connection)
        assert listing["total"] == 2
        assert [source["source"] for source in listing["sources"]] == [
            "first",
            "second",
        ]
        for source in listing["sources"]:
            assert source["import_kind"] == "legacy"
            assert source["active_count"] == 1
            for unknown in (
                "synced_at",
                "snapshot_sha256",
                "input_count",
                "new_count",
                "updated_count",
                "reopened_count",
                "closed_count",
                "unchanged_count",
            ):
                assert source[unknown] is None
        sync_jobs_with_receipt(connection, "first", DEMO[:1])
        assert get_source(connection, "first")["import_kind"] == "json"
        assert get_source(connection, "second")["import_kind"] == "legacy"


def test_read_connection_holds_one_snapshot_across_queries(tmp_path):
    path = tmp_path / "jobs.sqlite"
    with connect(path) as connection:
        sync_jobs_with_receipt(connection, "demo", DEMO[:1])
    with read_db(path) as reader:
        assert list_sources(reader)["total"] == 1
        with connect(path) as writer:
            sync_jobs_with_receipt(writer, "partner", DEMO[1:2])
        assert list_sources(reader)["total"] == 1
    with read_db(path) as reader:
        assert list_sources(reader)["total"] == 2


def test_cli_prints_receipt_and_requires_explicit_empty_confirmation(
    tmp_path, monkeypatch, capsys
):
    path = tmp_path / "jobs.sqlite"
    feed = tmp_path / "feed.json"
    feed.write_text(json.dumps(DEMO[:1]))
    monkeypatch.setenv("OPENJOBS_DB", str(path))
    monkeypatch.setattr(
        "sys.argv", ["openjobs", "import-json", str(feed), "--source", "demo"]
    )
    main()
    receipt = json.loads(capsys.readouterr().out)
    assert receipt["new_count"] == 1
    assert receipt["active_count"] == 1

    feed.write_text("[]")
    with pytest.raises(SystemExit) as exc:
        main()
    assert exc.value.code == 2
    assert "empty feed" in capsys.readouterr().err
    monkeypatch.setattr(
        "sys.argv",
        [
            "openjobs",
            "import-json",
            str(feed),
            "--source",
            "demo",
            "--allow-empty",
        ],
    )
    main()
    empty = json.loads(capsys.readouterr().out)
    assert empty["closed_count"] == 1
    assert empty["active_count"] == 0


def test_import_limits_reject_oversize_inputs_without_receipt(
    database,
    tmp_path,
    monkeypatch,
    capsys,
):
    monkeypatch.setattr(store, "MAX_SOURCE_JOBS", 1)
    with pytest.raises(ValueError, match="exceeds 1 jobs"):
        sync_jobs_with_receipt(database, "demo", DEMO[:2])
    with pytest.raises(ValueError, match="source_id exceeds"):
        sync_jobs_with_receipt(database, "demo", [{**DEMO[0], "source_id": "x" * 201}])
    with pytest.raises(ValueError, match="description exceeds"):
        sync_jobs_with_receipt(
            database,
            "demo",
            [
                {**DEMO[0], "description": "x" * (store.MAX_DESCRIPTION_CHARS + 1)},
            ],
        )
    monkeypatch.setattr(store, "MAX_TOTAL_DESCRIPTION_CHARS", 3)
    with pytest.raises(ValueError, match="feed descriptions exceed"):
        sync_jobs_with_receipt(database, "demo", [{**DEMO[0], "description": "abcd"}])
    assert list_sources(database)["total"] == 0

    feed = tmp_path / "too-large.json"
    feed.write_text(json.dumps(DEMO[:1]))
    monkeypatch.setattr(cli, "MAX_FEED_BYTES", 16)
    monkeypatch.setattr(
        "sys.argv",
        [
            "openjobs",
            "import-json",
            str(feed),
            "--source",
            "demo",
        ],
    )
    with pytest.raises(SystemExit) as exc:
        main()
    assert exc.value.code == 2
    assert "JSON feed exceeds" in capsys.readouterr().err
