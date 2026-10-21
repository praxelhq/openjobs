import json
import sqlite3
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from openjobs.api import create_app
from openjobs.store import connect, get_job, search_jobs, sync_jobs

DEMO = json.loads((Path(__file__).parent.parent / "examples/demo.json").read_text())


@pytest.fixture
def database(tmp_path):
    connection = connect(tmp_path / "jobs.sqlite")
    yield connection
    connection.close()


def test_search_filters_and_provenance(database):
    sync_jobs(database, "demo", DEMO)
    result = search_jobs(database, query="engineer", work_mode="remote")
    assert result["total"] == 2
    assert all(job["work_mode"] == "remote" for job in result["jobs"])
    assert all(job["source"] == "demo" and job["source_url"] for job in result["jobs"])
    assert search_jobs(database, location="Bengaluru")["total"] == 1
    assert search_jobs(database, company="Northstar")["total"] == 2


def test_reimport_keeps_id_and_first_seen_and_deactivates_missing(database):
    sync_jobs(database, "demo", DEMO)
    original = search_jobs(database, query="Backend")["jobs"][0]
    sync_jobs(database, "demo", DEMO[1:])
    assert get_job(database, original["id"]) is None
    retained = search_jobs(database, query="Product Designer")["jobs"][0]
    assert (
        retained["first_seen_at"]
        == search_jobs(database, company="Northstar")["jobs"][0]["first_seen_at"]
    )
    sync_jobs(database, "demo", DEMO)
    returned = get_job(database, original["id"])
    assert returned is not None
    assert returned["first_seen_at"] == original["first_seen_at"]


def test_invalid_feed_does_not_change_active_set(database):
    sync_jobs(database, "demo", DEMO)
    invalid = [{**DEMO[0], "source_url": "javascript:alert(1)"}]
    with pytest.raises(ValueError):
        sync_jobs(database, "demo", invalid)
    with pytest.raises(ValueError):
        sync_jobs(database, "demo", [{**DEMO[0], "title": None}])
    assert search_jobs(database)["total"] == len(DEMO)


def test_api_search_and_not_found(tmp_path):
    path = tmp_path / "jobs.sqlite"
    with connect(path) as connection:
        sync_jobs(connection, "demo", DEMO)
    client = TestClient(create_app(path))
    response = client.get("/v1/jobs", params={"query": "Python", "limit": 1})
    assert response.status_code == 200
    assert response.json()["total"] == 1
    assert response.json()["jobs"][0]["title"] == "Backend Engineer"
    assert client.get("/v1/jobs/no-such-id").status_code == 404
    assert client.get("/v1/jobs", params={"work_mode": "invalid"}).status_code == 422
    assert client.get("/").json()["jobs"] == "/v1/jobs"


def test_company_path_with_slash(tmp_path):
    path = tmp_path / "jobs.sqlite"
    with connect(path) as connection:
        sync_jobs(
            connection,
            "demo",
            [
                {**DEMO[0], "company": "Research / Design"},
                {**DEMO[1], "company": "Research / Design Labs"},
            ],
        )
    client = TestClient(create_app(path))
    assert client.get("/v1/companies/Research%20%2F%20Design/jobs").json()["total"] == 1
    assert (
        client.get("/v1/jobs", params={"company": "Research / Design"}).json()["total"]
        == 2
    )


def test_existing_preview_database_keeps_observation_time_after_upgrade(tmp_path):
    path = tmp_path / "jobs.sqlite"
    with connect(path) as connection:
        sync_jobs(connection, "demo", DEMO[:1])
        original = search_jobs(connection)["jobs"][0]
    with sqlite3.connect(path) as connection:
        connection.execute(
            "ALTER TABLE jobs RENAME COLUMN last_seen_at TO last_verified_at"
        )

    connection = connect(path)
    try:
        upgraded = get_job(connection, original["id"])
        assert upgraded is not None
        assert upgraded["last_seen_at"] == original["last_seen_at"]
    finally:
        connection.close()
    with sqlite3.connect(path) as connection:
        columns = {row[1] for row in connection.execute("PRAGMA table_info(jobs)")}
        assert "last_seen_at" in columns
        assert "last_verified_at" not in columns
    with connect(path) as connection:
        sync_jobs(connection, "demo", DEMO[:1])
        assert search_jobs(connection, query="Backend")["total"] == 1
