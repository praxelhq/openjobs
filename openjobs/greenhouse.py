"""Opt-in Greenhouse Job Board API reader for boards you may use."""

from __future__ import annotations

import json
import re
from html.parser import HTMLParser

import httpx

from .store import MAX_FEED_BYTES, MAX_SOURCE_JOBS


class _PlainText(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []

    def handle_data(self, data: str) -> None:
        self.parts.append(data)


def _plain_text(html: str) -> str:
    parser = _PlainText()
    parser.feed(html)
    return " ".join(" ".join(parser.parts).split())


def fetch_board(board_token: str, company: str) -> list[dict]:
    if not re.fullmatch(r"[a-zA-Z0-9_-]{1,80}", board_token):
        raise ValueError("invalid Greenhouse board token")
    if not company.strip():
        raise ValueError("company is required")
    url = f"https://boards-api.greenhouse.io/v1/boards/{board_token}/jobs"
    with httpx.Client(timeout=15, follow_redirects=False) as client:
        with client.stream("GET", url, params={"content": "true"}) as response:
            response.raise_for_status()
            body = bytearray()
            for chunk in response.iter_bytes():
                if len(body) + len(chunk) > MAX_FEED_BYTES:
                    raise ValueError(
                        f"Greenhouse response exceeds {MAX_FEED_BYTES} bytes"
                    )
                body.extend(chunk)
    payload = json.loads(body)
    if not isinstance(payload, dict) or not isinstance(payload.get("jobs"), list):
        raise ValueError("unexpected Greenhouse response")
    if len(payload["jobs"]) > MAX_SOURCE_JOBS:
        raise ValueError(f"Greenhouse response exceeds {MAX_SOURCE_JOBS} jobs")
    jobs = []
    for item in payload["jobs"]:
        if not isinstance(item, dict) or any(
            key not in item for key in ("id", "title", "absolute_url")
        ):
            raise ValueError("unexpected Greenhouse job")
        location = item.get("location") or {}
        if not isinstance(location, dict):
            raise ValueError("unexpected Greenhouse job location")
        jobs.append(
            {
                "source_id": str(item["id"]),
                "title": item["title"],
                "company": company.strip(),
                "location": location.get("name", ""),
                "work_mode": "unknown",  # Loose text is not remote eligibility.
                "description": _plain_text(item.get("content") or ""),
                "source_url": item["absolute_url"],
                "posted_at": None,  # The board API does not promise a posting date.
            }
        )
    return jobs
