"""Read-only job search API."""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import JSONResponse

from .store import (
    IndexUnavailableError,
    get_job,
    get_source,
    get_source_syncs,
    list_sources,
    read_db,
    search_jobs,
)


def create_app(database: Path | None = None) -> FastAPI:
    app = FastAPI(title="OpenJobs API", version="0.1.0")

    @app.exception_handler(IndexUnavailableError)
    async def unavailable(
        _request: Request, _exc: IndexUnavailableError
    ) -> JSONResponse:
        return JSONResponse(
            status_code=503,
            content={
                "detail": "No initialized job index is available; import a feed first"
            },
        )

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/ready")
    def ready() -> dict[str, int | str]:
        """Report whether this instance has successfully imported searchable data."""
        with read_db(database) as connection:
            sources = connection.execute(
                "SELECT COUNT(DISTINCT source) FROM source_syncs"
            ).fetchone()[0]
            indexed_jobs = connection.execute(
                "SELECT COUNT(*) FROM jobs WHERE active = 1"
            ).fetchone()[0]
        return {"status": "ready", "sources": sources, "indexed_jobs": indexed_jobs}

    @app.get("/v1/jobs")
    def jobs(
        query: str = Query("", max_length=200),
        location: str = Query("", max_length=100),
        company: str = Query("", max_length=100),
        work_mode: str = "",
        limit: int = Query(20, ge=1, le=100),
        offset: int = Query(0, ge=0),
    ) -> dict:
        try:
            with read_db(database) as connection:
                return search_jobs(
                    connection,
                    query=query,
                    location=location,
                    company=company,
                    work_mode=work_mode,
                    limit=limit,
                    offset=offset,
                )
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @app.get("/v1/jobs/{job_id}")
    def job_detail(job_id: str) -> dict:
        with read_db(database) as connection:
            job = get_job(connection, job_id)
        if job is None:
            raise HTTPException(status_code=404, detail="Job not found")
        return job

    @app.get("/v1/companies/{company:path}/jobs")
    def company_jobs(
        company: str, limit: int = Query(20, ge=1, le=100), offset: int = Query(0, ge=0)
    ) -> dict:
        with read_db(database) as connection:
            return search_jobs(
                connection,
                company=company,
                company_exact=True,
                limit=limit,
                offset=offset,
            )

    @app.get("/v1/sources")
    def sources(
        limit: int = Query(20, ge=1, le=100), offset: int = Query(0, ge=0)
    ) -> dict:
        with read_db(database) as connection:
            return list_sources(connection, limit=limit, offset=offset)

    @app.get("/v1/sources/{source}/syncs")
    def source_syncs(
        source: str,
        limit: int = Query(20, ge=1, le=100),
        offset: int = Query(0, ge=0),
    ) -> dict:
        with read_db(database) as connection:
            history = get_source_syncs(connection, source, limit=limit, offset=offset)
        if history is None:
            raise HTTPException(status_code=404, detail="Source not found")
        return history

    @app.get("/v1/sources/{source}")
    def source_detail(source: str) -> dict:
        with read_db(database) as connection:
            receipt = get_source(connection, source)
        if receipt is None:
            raise HTTPException(status_code=404, detail="Source not found")
        return receipt

    @app.get("/", include_in_schema=False)
    def index() -> dict[str, str]:
        return {
            "name": "OpenJobs",
            "api_docs": "/docs",
            "jobs": "/v1/jobs",
            "sources": "/v1/sources",
            "health": "/health",
            "ready": "/ready",
        }

    return app


app = create_app()
