import json

import httpx
import pytest

from openjobs import cli, praxy

JOB = {
    "job_key": "abc",
    "title": "Engineer",
    "organization": "Acme",
    "url": "https://acme.example/jobs/1",
    "status": "open",
    "first_seen": "2026-10-22T00:00:00Z",
    "last_seen": "2026-10-22T00:00:00Z",
    "source": "greenhouse",
    "source_slug": "acme",
    "has_salary": False,
    "source_endpoint": "https://boards.greenhouse.io/acme",
    "directory_verified_at": "2026-10-21T00:00:00Z",
    "description_snippet": "Build reliable software.",
    "description_text": "Build reliable software with the team.",
    "remote_derived": True,
    "locations": [{"name": "Bengaluru, India"}],
    "locations_derived": [{
        "city": "Bengaluru", "country": "IN", "country_code": "IN",
        "lat": 12.97, "lng": 77.59,
    }],
    "cities_derived": ["Bengaluru"],
    "countries_derived": ["IN"],
    "employment_type": ["FULL_TIME"],
    "department": "Engineering",
    "salary": "₹20L–₹30L",
    "salary_min_derived": 2000000,
    "salary_max_derived": 3000000,
    "salary_currency_derived": "INR",
    "salary_period_derived": "YEAR",
    "salary_derived": {"min": 2000000, "max": 3000000,
                       "currency": "INR", "period": "YEAR"},
    "taxonomy": {"family": "engineering", "subfamily": "software_engineering",
                 "skill_clusters": ["backend"]},
    "company_key": "acme",
    "api_key": "must-not-echo",
}


def test_search_uses_fixed_host_key_header_and_preserves_provenance(monkeypatch):
    monkeypatch.setenv("PRAXY_JOBS_KEY", "test-secret")

    def respond(request):
        assert request.method == "GET"
        assert request.url.scheme == "https"
        assert request.url.host == "praxyjobs.com"
        assert request.url.path == "/v1/jobs/search"
        assert request.url.params["q"] == "engineer"
        assert request.url.params["country"] == "IN"
        assert request.url.params["limit"] == "1"
        assert request.headers["x-api-key"] == "test-secret"
        assert "test-secret" not in str(request.url)
        return httpx.Response(
            200,
            json={"results": [JOB], "total_estimate": 42, "next_cursor": "opaque-1"},
        )

    page = praxy.search_praxy_jobs(
        query="engineer",
        country="in",
        limit=1,
        transport=httpx.MockTransport(respond),
    )
    assert page["provider"] == "praxyjobs.com"
    assert page["total_estimate"] == 42
    assert page["next_cursor"] == "opaque-1"
    job = page["jobs"][0]
    assert job["company"] == "Acme"
    assert job["source_url"] == "https://acme.example/jobs/1"
    assert job["source"] == "greenhouse"
    assert job["source_slug"] == "acme"
    assert job["source_endpoint"] == "https://boards.greenhouse.io/acme"
    assert job["directory_verified_at"] == "2026-10-21T00:00:00Z"
    assert job["organization"] == job["company"] == "Acme"
    assert job["url"] == job["source_url"]
    assert job["locations_derived"] == JOB["locations_derived"]
    assert job["cities_derived"] == ["Bengaluru"]
    assert job["employment_type"] == ["FULL_TIME"]
    assert job["salary_derived"] == JOB["salary_derived"]
    assert job["salary_currency_derived"] == "INR"
    assert job["taxonomy"] == JOB["taxonomy"]
    assert "api_key" not in job
    assert "description_text" not in job


def test_search_forwards_cursor_and_optional_description(monkeypatch):
    monkeypatch.setenv("PRAXY_JOBS_KEY", "test-secret")

    def respond(request):
        assert request.url.params["cursor"] == "opaque-1"
        assert request.url.params["include_description"] == "true"
        assert request.url.params["exclude_duplicates"] == "true"
        assert request.url.params["remote"] == "only"
        assert request.url.params["source"] == "greenhouse"
        return httpx.Response(200, json={"results": [JOB], "total_estimate": 1})

    page = praxy.search_praxy_jobs(
        cursor="opaque-1",
        remote="only",
        source="greenhouse",
        include_description=True,
        exclude_duplicates=True,
        transport=httpx.MockTransport(respond),
    )
    assert page["next_cursor"] is None
    assert page["jobs"][0]["description_text"] == JOB["description_text"]


def test_search_requires_key_and_rejects_bad_inputs(monkeypatch):
    monkeypatch.delenv("PRAXY_JOBS_KEY", raising=False)
    never_call = httpx.MockTransport(lambda _request: pytest.fail("network called"))
    with pytest.raises(praxy.PraxyJobsError, match="PRAXY_JOBS_KEY"):
        praxy.search_praxy_jobs(transport=never_call)
    monkeypatch.setenv("PRAXY_JOBS_KEY", "test-secret")
    for kwargs in (
        {"query": "x" * 501},
        {"limit": 101},
        {"country": "India"},
        {"remote": "maybe"},
        {"status": "draft"},
    ):
        with pytest.raises(praxy.PraxyJobsError):
            praxy.search_praxy_jobs(transport=never_call, **kwargs)


@pytest.mark.parametrize(
    ("status", "headers", "expected"),
    [
        (402, {}, "key or plan"),
        (409, {}, "retry without a cursor"),
        (429, {"Retry-After": "42"}, "retry after 42 seconds"),
    ],
)
def test_errors_are_actionable_without_key(monkeypatch, status, headers, expected):
    monkeypatch.setenv("PRAXY_JOBS_KEY", "test-secret")
    transport = httpx.MockTransport(
        lambda _request: httpx.Response(
            status,
            headers=headers,
            json={"detail": "test-secret"},
        )
    )
    with pytest.raises(praxy.PraxyJobsError, match=expected) as exc:
        praxy.search_praxy_jobs(transport=transport)
    assert "test-secret" not in str(exc.value)


def test_rejects_malformed_or_oversized_pages(monkeypatch):
    monkeypatch.setenv("PRAXY_JOBS_KEY", "test-secret")
    malformed = httpx.MockTransport(
        lambda _request: httpx.Response(
            200,
            json={"results": [{"job_key": "abc"}], "total_estimate": 1},
        )
    )
    with pytest.raises(praxy.PraxyJobsError, match="incomplete job"):
        praxy.search_praxy_jobs(transport=malformed)
    monkeypatch.setattr(praxy, "MAX_RESPONSE_BYTES", 10)
    large = httpx.MockTransport(lambda _request: httpx.Response(200, content=b"x" * 11))
    with pytest.raises(praxy.PraxyJobsError, match="smaller limit"):
        praxy.search_praxy_jobs(transport=large)


def test_cli_search_does_not_touch_local_index(tmp_path, monkeypatch, capsys):
    path = tmp_path / "jobs.sqlite"
    monkeypatch.setenv("OPENJOBS_DB", str(path))
    monkeypatch.setattr(
        "sys.argv",
        [
            "openjobs",
            "search-praxy",
            "engineer",
            "--country",
            "IN",
            "--limit",
            "1",
        ],
    )
    seen = {}

    def fake_search(**kwargs):
        seen.update(kwargs)
        return {
            "provider": "praxyjobs.com",
            "jobs": [],
            "total_estimate": 0,
            "next_cursor": None,
            "limit": 1,
        }

    monkeypatch.setattr(cli, "search_praxy_jobs", fake_search)
    cli.main()
    assert seen["query"] == "engineer"
    assert seen["country"] == "IN"
    assert seen["limit"] == 1
    assert json.loads(capsys.readouterr().out)["provider"] == "praxyjobs.com"
    assert not path.exists()
