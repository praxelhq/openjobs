"""One-page search against Praxy Jobs' keyed hosted API.

This module never imports hosted results into the local snapshot database.
"""

from __future__ import annotations

import json
import os
import re
from typing import Any
from urllib.parse import urlparse

import httpx

BASE_URL = "https://praxyjobs.com/v1"
MAX_RESPONSE_BYTES = 10 * 1024 * 1024

# The hosted API has richer typed fields than the local index. Keep its known
# public job fields alongside OpenJobs aliases without forwarding unknown data.
PROVIDER_JOB_FIELDS = (
    "job_key",
    "external_id",
    "title",
    "title_clean",
    "organization",
    "company_key",
    "url",
    "status",
    "closed_at",
    "close_reason",
    "first_seen",
    "last_seen",
    "date_posted",
    "locations",
    "locations_derived",
    "cities_derived",
    "regions_derived",
    "countries_derived",
    "remote_derived",
    "visa_sponsorship_derived",
    "security_clearance_derived",
    "summary_derived",
    "responsibilities_derived",
    "qualifications_must_have_derived",
    "qualifications_preferred_derived",
    "education_derived",
    "certifications_derived",
    "employment_type",
    "department",
    "salary",
    "salary_min_derived",
    "salary_max_derived",
    "salary_currency_derived",
    "salary_period_derived",
    "has_salary",
    "salary_derived",
    "taxonomy",
    "language_derived",
    "description_snippet",
    "duplicate_group_id",
    "seo_indexable",
    "seo_canonical_job_key",
    "source",
    "source_slug",
    "source_endpoint",
    "directory_verified_at",
)


class PraxyJobsError(ValueError):
    """A safe, actionable hosted-search error with no credential material."""


def _validate(
    query: str,
    country: str,
    city: str,
    company: str,
    source: str,
    remote: str,
    status: str,
    limit: int,
    cursor: str,
) -> None:
    for name, value, maximum in (
        ("query", query, 500),
        ("city", city, 500),
        ("company", company, 500),
        ("source", source, 500),
        ("cursor", cursor, 4096),
    ):
        if not isinstance(value, str) or len(value) > maximum:
            raise PraxyJobsError(f"{name} must be at most {maximum} characters")
    if (
        not isinstance(country, str)
        or len(country) > 200
        or (country and not re.fullmatch(r"[A-Za-z]{2}(,[A-Za-z]{2})*", country))
    ):
        raise PraxyJobsError("country must be comma-separated two-letter codes")
    if remote not in {"", "only", "exclude"}:
        raise PraxyJobsError("remote must be only or exclude")
    if status not in {"open", "closed", "all"}:
        raise PraxyJobsError("status must be open, closed, or all")
    if not isinstance(limit, int) or isinstance(limit, bool) or not 1 <= limit <= 100:
        raise PraxyJobsError("limit must be between 1 and 100")


def _job(raw: Any, *, include_description: bool) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise PraxyJobsError("Praxy Jobs returned an invalid job")
    required = (
        "job_key",
        "title",
        "organization",
        "url",
        "status",
        "first_seen",
        "last_seen",
        "source",
        "source_slug",
        "has_salary",
    )
    if any(key not in raw for key in required):
        raise PraxyJobsError("Praxy Jobs returned an incomplete job")
    for key in required[:-1]:
        if not isinstance(raw[key], str):
            raise PraxyJobsError("Praxy Jobs returned an invalid job")
    if not isinstance(raw["has_salary"], bool):
        raise PraxyJobsError("Praxy Jobs returned an invalid job")
    try:
        url = urlparse(raw["url"])
    except ValueError as exc:
        raise PraxyJobsError("Praxy Jobs returned an invalid source URL") from exc
    if (
        url.scheme not in {"http", "https"}
        or not url.netloc
        or url.username
        or url.password
    ):
        raise PraxyJobsError("Praxy Jobs returned an invalid source URL")

    job: dict[str, Any] = {
        field: raw[field] for field in PROVIDER_JOB_FIELDS if field in raw
    }
    job.update({
        "company": raw["organization"],
        "source_url": raw["url"],
        "first_seen_at": raw["first_seen"],
        "last_seen_at": raw["last_seen"],
    })
    if "date_posted" in raw:
        job["posted_at"] = raw["date_posted"]
    if include_description and "description_text" in raw:
        job["description_text"] = raw["description_text"]
    return job


def _error_for_response(response: httpx.Response) -> PraxyJobsError:
    status = response.status_code
    if status in {401, 402, 403}:
        return PraxyJobsError(
            f"Praxy Jobs rejected the API key or plan (HTTP {status})"
        )
    if status == 409:
        return PraxyJobsError("Praxy Jobs cursor expired; retry without a cursor")
    if status == 429:
        retry_after = response.headers.get("Retry-After", "")
        if re.fullmatch(r"\d{1,6}", retry_after):
            return PraxyJobsError(
                f"Praxy Jobs rate limit reached; retry after {retry_after} seconds"
            )
        return PraxyJobsError("Praxy Jobs rate limit reached; retry later")
    return PraxyJobsError(f"Praxy Jobs search failed (HTTP {status})")


def search_praxy_jobs(
    *,
    query: str = "",
    country: str = "",
    city: str = "",
    company: str = "",
    source: str = "",
    remote: str = "",
    status: str = "open",
    exclude_duplicates: bool = False,
    include_description: bool = False,
    limit: int = 20,
    cursor: str = "",
    transport: httpx.BaseTransport | None = None,
) -> dict[str, Any]:
    """Search one hosted page. The caller may pass the returned cursor unchanged."""
    _validate(query, country, city, company, source, remote, status, limit, cursor)
    key = os.environ.get("PRAXY_JOBS_KEY", "").strip()
    if not key:
        raise PraxyJobsError("PRAXY_JOBS_KEY is required for hosted search")
    params: dict[str, str | int] = {"limit": limit, "status": status}
    for name, value in (
        ("q", query),
        ("country", country.upper()),
        ("city", city),
        ("company", company),
        ("source", source),
        ("remote", remote),
        ("cursor", cursor),
    ):
        if value:
            params[name] = value
    if exclude_duplicates:
        params["exclude_duplicates"] = "true"
    if include_description:
        params["include_description"] = "true"

    try:
        with httpx.Client(
            timeout=httpx.Timeout(10.0, connect=5.0),
            follow_redirects=False,
            transport=transport,
        ) as client:
            with client.stream(
                "GET",
                f"{BASE_URL}/jobs/search",
                headers={"X-API-Key": key, "Accept": "application/json"},
                params=params,
            ) as response:
                if response.status_code != 200:
                    raise _error_for_response(response)
                body = bytearray()
                for chunk in response.iter_bytes():
                    if len(body) + len(chunk) > MAX_RESPONSE_BYTES:
                        raise PraxyJobsError(
                            f"Praxy Jobs response exceeds {MAX_RESPONSE_BYTES} bytes; "
                            "use a smaller limit"
                        )
                    body.extend(chunk)
    except httpx.TimeoutException as exc:
        raise PraxyJobsError("Praxy Jobs request timed out") from exc
    except httpx.HTTPError as exc:
        raise PraxyJobsError("Praxy Jobs request failed") from exc

    try:
        payload = json.loads(body)
    except ValueError as exc:
        raise PraxyJobsError("Praxy Jobs returned invalid JSON") from exc
    if (
        not isinstance(payload, dict)
        or not isinstance(payload.get("results"), list)
        or not isinstance(payload.get("total_estimate"), int)
        or isinstance(payload["total_estimate"], bool)
        or payload["total_estimate"] < 0
    ):
        raise PraxyJobsError("Praxy Jobs returned an invalid search page")
    next_cursor = payload.get("next_cursor")
    if next_cursor is not None and not isinstance(next_cursor, str):
        raise PraxyJobsError("Praxy Jobs returned an invalid cursor")
    if len(payload["results"]) > limit:
        raise PraxyJobsError("Praxy Jobs returned more jobs than requested")
    return {
        "provider": "praxyjobs.com",
        "jobs": [
            _job(raw, include_description=include_description)
            for raw in payload["results"]
        ],
        "total_estimate": payload["total_estimate"],
        "next_cursor": next_cursor,
        "limit": limit,
    }
