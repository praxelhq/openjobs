from contextlib import nullcontext

import httpx
import pytest

from openjobs import greenhouse


def test_greenhouse_normalizes_documented_board_response(monkeypatch):
    class FakeClient:
        def __init__(self, **kwargs):
            assert kwargs["follow_redirects"] is False

        def __enter__(self):
            return self

        def __exit__(self, *_):
            pass

        def get(self, url, params):
            assert url == "https://boards-api.greenhouse.io/v1/boards/acme/jobs"
            assert params == {"content": "true"}
            return httpx.Response(
                200,
                json={
                    "jobs": [
                        {
                            "id": 123,
                            "title": "Engineer",
                            "location": {"name": "Remote"},
                            "absolute_url": (
                                "https://boards.greenhouse.io/acme/jobs/123"
                            ),
                            "content": (
                                "<p>Build <strong>reliable</strong> software.</p>"
                            ),
                        }
                    ]
                },
                request=httpx.Request("GET", url),
            )

        def stream(self, method, url, params):
            assert method == "GET"
            return nullcontext(self.get(url, params))

    monkeypatch.setattr(greenhouse.httpx, "Client", FakeClient)
    jobs = greenhouse.fetch_board("acme", "Acme")
    assert jobs == [
        {
            "source_id": "123",
            "title": "Engineer",
            "company": "Acme",
            "location": "Remote",
            "work_mode": "unknown",
            "description": "Build reliable software.",
            "source_url": "https://boards.greenhouse.io/acme/jobs/123",
            "posted_at": None,
        }
    ]


def test_greenhouse_rejects_path_tokens_before_fetch():
    with pytest.raises(ValueError):
        greenhouse.fetch_board("../other", "Acme")


def test_greenhouse_stream_stops_at_byte_limit(monkeypatch):
    class FakeClient:
        def __init__(self, **_kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *_):
            pass

        def stream(self, _method, url, _params=None, **kwargs):
            response = httpx.Response(
                200,
                content=b"x" * 17,
                request=httpx.Request("GET", url),
            )
            return nullcontext(response)

    monkeypatch.setattr(greenhouse.httpx, "Client", FakeClient)
    monkeypatch.setattr(greenhouse, "MAX_FEED_BYTES", 16)
    with pytest.raises(ValueError, match="exceeds"):
        greenhouse.fetch_board("acme", "Acme")


def test_greenhouse_rejects_too_many_jobs_before_normalization(monkeypatch):
    class FakeClient:
        def __init__(self, **_kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *_):
            pass

        def stream(self, _method, url, _params=None, **_kwargs):
            response = httpx.Response(
                200,
                json={"jobs": [{}, {}]},
                request=httpx.Request("GET", url),
            )
            return nullcontext(response)

    monkeypatch.setattr(greenhouse.httpx, "Client", FakeClient)
    monkeypatch.setattr(greenhouse, "MAX_SOURCE_JOBS", 1)
    with pytest.raises(ValueError, match="exceeds 1 jobs"):
        greenhouse.fetch_board("acme", "Acme")
