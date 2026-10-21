# OpenJobs contributor notes for coding agents

Read [README.md](README.md) for the product promise, [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for the data flow, and [CONTRIBUTING.md](CONTRIBUTING.md) for the review path. This file describes repository boundaries; it does not override the user's request.

## Project map

| Path | Responsibility |
| --- | --- |
| `openjobs/store.py` | SQLite schema, validation, atomic snapshots, search, and source receipts. |
| `openjobs/cli.py`, `openjobs/greenhouse.py` | Explicit local imports and the narrowly scoped Greenhouse fetch. |
| `openjobs/praxy.py` | One direct, keyed Praxy Jobs API search page; no local persistence. |
| `openjobs/api.py` | Read-only HTTP queries. |
| `openjobs/mcp_server.py` | Five read-only local stdio tools plus one explicit direct Praxy Jobs search tool. |
| `web/` | Public-source anonymous search app; same-origin server route to fixed first-party consumer search. Production launch remains gated. |
| `examples/demo.json` | Fictional jobs only. |
| `tests/` | Contract and failure-path tests. |
| `docs/` | User recipes, source policy, architecture, and release gates. |

## Invariants

- One import is a **complete snapshot of one source**. Validate it before changing the active set. A failed fetch or validation error must preserve the previous snapshot and must not create a success receipt.
- `source` plus `source_id` identifies a job. Reimporting it preserves the public ID and `first_seen_at`.
- Successful import receipts and `last_seen_at` record what OpenJobs observed. A `legacy` baseline from an older database is migration metadata with unknown timestamp and change counts. Neither verifies live URLs, permission, or that a role is still open.
- The HTTP API and five local-index MCP tools cannot import or fetch. `search-praxy` and MCP `search_praxy_jobs` make a direct keyed call to the fixed Praxy Jobs API and must never persist or proxy those results into the local index implicitly. Fetchers use fixed hosts or narrowly reviewed allowlists and never accept arbitrary remote URLs.
- `PRAXY_JOBS_KEY` is an environment secret. Never expose it through tool output, errors, logs, tests, examples, or committed configuration. Hosted data remains under the Praxy Jobs subscription and data license; this repository's MIT license covers code only.
- The `web/` service uses a **different** server-only `OPENJOBS_CONSUMER_SEARCH_KEY`. Never expose it to browser JavaScript, logs, examples, or public errors. Public search requires bounded inputs/responses and shared request limits; a working build is not deployment proof.
- Do not bundle real third-party listings, credentials, candidate information, or private Praxy data. Source code under MIT does not license someone else's job data.
- Do not describe the existing PraxyJobs.com hosted API as this repository's deployment unless its actual release and commit are verified.

## Useful checks

```bash
uv sync --extra test
uv run pytest -q
uv run python -m compileall -q openjobs
docker build -t openjobs:local .
cd web && npm ci && npm run test && npm run typecheck && npm run build
```

Use `OPENJOBS_DB=/absolute/path/jobs.sqlite` for isolated manual tests. Work from a clean checkout when verifying first-run docs. Document observable behavior and unresolved limitations; do not add unearned badges, synthetic live counts, or unsupported freshness claims.
