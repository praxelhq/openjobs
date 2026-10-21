# Contributing to OpenJobs

OpenJobs is a job discovery project: a public search experience is in development, while the current Python package offers direct Praxy Jobs CLI/MCP search and a self-hosted index for **authorized** feeds. A useful contribution makes a real user task clearer or more reliable. Bug reports, reproducible docs fixes, source adapters with a clear rights model, and tests for a failure case are welcome.

## Start locally

Install Python 3.11+ and [uv](https://docs.astral.sh/uv/), then from the repository root:

```bash
uv sync --extra test
uv run openjobs import-json examples/demo.json --source demo
uv run pytest -q
```

The sample data is fictional. The import writes `data/jobs.sqlite` by default; set `OPENJOBS_DB` to an absolute path to isolate your test database. Run `uv run uvicorn openjobs.api:app --host 127.0.0.1` for the local-index API, or `uv run openjobs-mcp` for stdio MCP. The [local API/MCP recipes](docs/API_AND_MCP.md) show what each command should return. The separate [Praxy Jobs live-search path](docs/PRAXY_LIVE.md) requires your own activated key. CI also builds the Docker image and runs a smoke check.

For a change under [`web/`](web/README.md), use Node 22+ and run `npm ci`, `npm run test`, `npm run typecheck`, and `npm run build` from that directory. Local live search additionally needs a dedicated consumer-search service key and shared Redis; the web README describes the gated setup. Unit tests and a successful build do not establish that the public domain is live.

## Choose a focused change

- **Documentation or first-run bug:** open a small PR directly. Include the command or link you tried and what you expected.
- **Public search experience:** describe the anonymous search, filter, source-link, mobile, or error-state task you tested. Include a screenshot only if it shows the actual running code; never paste an API key or a real applicant record.
- **Behavior change:** file an issue first with a failing example and the proposed contract. Keep API and MCP results consistent.
- **Source adapter:** open an issue with the official endpoint, stable ID, completeness/pagination behavior, and the intended data-use permission. See [source policy](docs/SOURCE_POLICY.md) before writing the fetcher.

The importer is the only **local-index** write path. HTTP and the five local-index MCP tools stay read-only; `search_praxy_jobs` is a separate direct network search without persistence. A source fetch must use a fixed host or narrow allowlist; it cannot expose arbitrary URL fetching through a remote request. Never close existing jobs after a partial or failed fetch. An empty successful snapshot can close every job for that source, so it must require deliberate confirmation. Preserve a source's original URL and stable ID, and keep unknown posting dates or work modes unknown.

## Pull request checklist

- [ ] The change has a clear user or maintainer problem and a bounded scope.
- [ ] Tests cover the behavior at its trust boundary: malformed input, duplicate IDs, failed fetch, reimport, or empty results as applicable. Documentation-only edits do not need mirror tests.
- [ ] `uv run pytest -q` passes. If Docker or install behavior changed, run the relevant Docker path too.
- [ ] For `web/` changes, `npm run test`, `npm run typecheck`, and `npm run build` pass; verify a real anonymous search on staging when changing the server route or result UI.
- [ ] Public docs, CLI help, API schema, and MCP descriptions agree with the implementation.
- [ ] Hosted Praxy Jobs changes use mocked HTTP responses in tests; no live subscription key or production request is needed in CI.
- [ ] No secrets, cookies, resumes, candidate records, harvested listing dumps, or unlicensed data are committed.
- [ ] A new source states its rights and removal path; a screenshot of a public endpoint is not permission.

Explain what changed, why, how you tested it, and what remains unverified. Keep PRs reviewable; separate unrelated cleanup. Follow the [Code of Conduct](CODE_OF_CONDUCT.md), and report vulnerabilities privately via [SECURITY.md](SECURITY.md).
