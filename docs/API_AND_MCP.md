# Local index API and MCP recipes

The OpenJobs HTTP API and five local-index MCP tools read the same SQLite file. Import with the CLI first; neither the HTTP API nor those five tools can change the local index. A **separate** `search_praxy_jobs` MCP tool makes a direct keyed request to PraxyJobs.com and does not store results locally. See [live Praxy Jobs search](PRAXY_LIVE.md) for that path. The commands below use the eight **fictional** listings in [`examples/demo.json`](../examples/demo.json).

## Start the local API

From the repository root, with Python 3.11+ and [uv](https://docs.astral.sh/uv/) installed:

```bash
uv sync
export OPENJOBS_DB="$PWD/data/jobs.sqlite"
uv run openjobs import-json examples/demo.json --source demo
uv run uvicorn openjobs.api:app --host 127.0.0.1
```

Keep that terminal open. In a second terminal:

```bash
curl -fsS 'http://127.0.0.1:8000/health'
curl -fsS 'http://127.0.0.1:8000/ready'
curl -fsS 'http://127.0.0.1:8000/v1/jobs?query=engineer&work_mode=remote'
```

The search returns two demo jobs. It has this envelope:

```json
{
  "jobs": [{"id": "job_…", "title": "…", "source": "demo", "source_url": "https://example.com/…", "first_seen_at": "…", "last_seen_at": "…"}],
  "total": 2,
  "limit": 20,
  "offset": 0
}
```

The ellipses above mark fields that depend on the import time or selected job. They are not a verbatim server response. For the full schema and a browser-based request form, open [`/docs`](http://127.0.0.1:8000/docs) on your own machine.

### Common REST tasks

| Task | Request |
| --- | --- |
| Search keywords | `GET /v1/jobs?query=engineer` |
| Filter by location and work mode | `GET /v1/jobs?location=India&work_mode=remote` |
| Filter by company name | `GET /v1/jobs?company=Northstar` (case-insensitive substring) |
| Paginate | `GET /v1/jobs?limit=10&offset=10` |
| One job | `GET /v1/jobs/{job_id}` |
| Exact company | `GET /v1/companies/{company}/jobs` (URL-encode the company name) |
| Latest source receipts | `GET /v1/sources` |
| One source's latest receipt | `GET /v1/sources/{source}` |
| One source's receipt history | `GET /v1/sources/{source}/syncs?limit=20&offset=0` |
| Process and data readiness | `GET /health` and `GET /ready` |

`limit` is 1–100; `offset` starts at zero. A search with no matches returns `jobs: []` and `total: 0`. A missing job or source returns HTTP 404. Invalid filters return HTTP 422. If no initialized index is available, reads return HTTP 503. `/health` says the process is serving requests; `/ready` returns 503 when the database is missing or uninitialized and 200 when its schema is readable. The 200 response may report `sources: 0` and `indexed_jobs: 0`; check those counts separately if your service requires imported data. Jobs returned by search or detail are active in the latest successful snapshot of their source. The API does not verify that the source link still works.

To inspect just the provenance fields with [jq](https://jqlang.github.io/jq/) if installed:

```bash
curl -fsS 'http://127.0.0.1:8000/v1/jobs?query=engineer&work_mode=remote' \
  | jq '{total, jobs: [.jobs[] | {title, company, source, source_url, last_seen_at}]}'
```

The receipt endpoints describe **imports**, not live job checks. A successful import receipt has `id`, `source`, `import_kind`, `synced_at`, `snapshot_sha256`, `input_count`, `active_count`, and `new_count` / `updated_count` / `reopened_count` / `closed_count` / `unchanged_count`. A `legacy` baseline record created during an older-database upgrade has `active_count`, but its observation time, digest, input count, and change counts are `null`; it does not prove a new import succeeded. `GET /v1/sources` returns `{sources, total, limit, offset}` with each source's latest record; the history route returns `{source, syncs, total, limit, offset}` newest first. See [source policy](SOURCE_POLICY.md) for what those fields can and cannot prove.

### Import guardrails

The CLI accepts at most **50 MiB** for a JSON file or one streamed Greenhouse response, **10,000 jobs per source snapshot**, **100,000 characters in one description**, and **20 million description characters across the snapshot**. Field caps are 200 characters for `source_id`, 500 each for `title`, `company`, and `location`, and 4,096 for `source_url`. Oversized input fails before it replaces an existing source snapshot. These bounds protect a local import; they do not authorize storage or redistribution of the feed.

## Connect a local MCP client

OpenJobs runs over **stdio**. Import the sample first and give the server an absolute path to that same database. A client that accepts an MCP server map can use:

```json
{
  "mcpServers": {
    "openjobs": {
      "command": "/absolute/path/to/openjobs/.venv/bin/openjobs-mcp",
      "env": {
        "OPENJOBS_DB": "/absolute/path/to/openjobs/data/jobs.sqlite"
      }
    }
  }
}
```

Your client's surrounding configuration may differ; the important values for **local-index tools** are the executable path and `OPENJOBS_DB`. Those tools are `search_jobs`, `get_job_details`, `get_company_jobs`, `list_sources`, and `get_source_syncs`. `search_jobs` accepts `query`, `location`, `work_mode`, `limit`, and `offset`. `get_job_details` takes a job ID returned by search. `get_company_jobs` takes a company name. `list_sources` accepts `limit` and `offset`; `get_source_syncs` takes a `source` plus optional `limit` and `offset`.

The sixth tool, `search_praxy_jobs`, uses `PRAXY_JOBS_KEY` from the **MCP process environment** to query the hosted API directly. It works without a local index, has different filters and cursor pagination, and creates no local receipt. Use your client's private environment/secret settings for the key; do not commit a config file containing it. See the [hosted MCP guide](PRAXY_LIVE.md#mcp-tool).

Try a call in your client with `search_jobs({"query":"engineer","work_mode":"remote","limit":5})`. It should return the same two fictional listings as the REST request above. No remote MCP endpoint or client-specific installer is included in this release.

You can verify the stdio round trip without configuring a desktop client. From the repository root, after the demo import:

```bash
OPENJOBS_DB="$PWD/data/jobs.sqlite" uv run python - <<'PY'
import asyncio
import os
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

async def main():
    server = StdioServerParameters(
        command=str(Path('.venv/bin/openjobs-mcp').resolve()),
        env=os.environ.copy(),
    )
    async with stdio_client(server) as (reader, writer):
        async with ClientSession(reader, writer) as client:
            await client.initialize()
            jobs = await client.call_tool(
                'search_jobs', {'query': 'engineer', 'work_mode': 'remote'}
            )
            print('remote engineer jobs:', jobs.structured_content['total'])
            sources = await client.call_tool('list_sources', {})
            print('sources:', sources.structured_content['total'])

asyncio.run(main())
PY
```

Against the fictional sample, this prints `remote engineer jobs: 2` and `sources: 1`. This uses the MCP Python SDK already installed with OpenJobs; it does not call a hosted service.

## Keep the interfaces in sync

For **local-index operations**, the API process, MCP process, and import CLI must point at **the same database file**. By default, `data/jobs.sqlite` is relative to each process's working directory. Set `OPENJOBS_DB` to an absolute path when running outside the repository root. The direct `search-praxy` CLI command and `search_praxy_jobs` MCP tool do not use this database.

Docker Compose stores its database in a named container volume. A host-based MCP process will not automatically read that volume; use a host import or mount the same database intentionally. The included Compose configuration only binds the HTTP API to host loopback.

If you are upgrading a preview checkout with an older database, run one valid import with the updated CLI before starting API or MCP. The CLI initializes the receipt schema; read-only processes cannot migrate it. Existing sources receive a `legacy` baseline record with `null` observation time, digest, input count, and historical change counts. A pre-upgrade database read directly may return HTTP 503 until the CLI has upgraded it. The valid import records normal change counts for its own source.
