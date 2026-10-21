"""Local index tools and one direct hosted Praxy Jobs search tool."""

from __future__ import annotations

from typing import Any

from mcp.server.mcpserver import MCPServer

from .praxy import search_praxy_jobs as search_hosted_jobs
from .store import (
    get_job,
    read_db,
    search_jobs,
)
from .store import (
    get_source_syncs as get_source_syncs_store,
)
from .store import (
    list_sources as list_source_receipts,
)

mcp = MCPServer("openjobs")


@mcp.tool(name="search_jobs", structured_output=True)
def search_jobs_tool(
    query: str = "",
    location: str = "",
    work_mode: str = "",
    limit: int = 20,
    offset: int = 0,
) -> dict[str, Any]:
    """Search indexed jobs by keywords, location, and remote/hybrid/onsite mode."""
    with read_db() as connection:
        return search_jobs(
            connection,
            query=query,
            location=location,
            work_mode=work_mode,
            limit=limit,
            offset=offset,
        )


@mcp.tool(structured_output=True)
def get_job_details(job_id: str) -> dict[str, Any]:
    """Get one job with its original source link and provenance."""
    with read_db() as connection:
        job = get_job(connection, job_id)
        if job is None:
            raise ValueError("Job not found")
        return job


@mcp.tool(structured_output=True)
def get_company_jobs(company: str, limit: int = 20, offset: int = 0) -> dict[str, Any]:
    """List indexed jobs for a company."""
    if not company.strip():
        raise ValueError("company is required")
    with read_db() as connection:
        return search_jobs(
            connection, company=company, company_exact=True, limit=limit, offset=offset
        )


@mcp.tool(structured_output=True)
def list_sources(limit: int = 20, offset: int = 0) -> dict[str, Any]:
    """List each source's latest import receipt and observed change counts."""
    with read_db() as connection:
        return list_source_receipts(connection, limit=limit, offset=offset)


@mcp.tool(structured_output=True)
def get_source_syncs(source: str, limit: int = 20, offset: int = 0) -> dict[str, Any]:
    """Get a source's import history; receipts do not prove jobs are still live."""
    if not source.strip():
        raise ValueError("source is required")
    with read_db() as connection:
        history = get_source_syncs_store(connection, source, limit=limit, offset=offset)
        if history is None:
            raise ValueError("Source not found")
        return history


@mcp.tool(structured_output=True)
def search_praxy_jobs(
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
) -> dict[str, Any]:
    """Search one hosted Praxy Jobs page using PRAXY_JOBS_KEY; no local import."""
    return search_hosted_jobs(
        query=query,
        country=country,
        city=city,
        company=company,
        source=source,
        remote=remote,
        status=status,
        exclude_duplicates=exclude_duplicates,
        include_description=include_description,
        limit=limit,
        cursor=cursor,
    )


def main() -> None:
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
