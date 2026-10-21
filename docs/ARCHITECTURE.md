# Architecture

OpenJobs has two **developer** data paths and a separate public website path. The developer **live path** makes one direct, keyed Praxy Jobs API request from the CLI or local MCP server and returns a normalized page without importing it. The **local path** turns permitted, complete feed snapshots into a SQLite index. The CLI is that index's only writer; HTTP and five MCP tools read the same file. The planned website's server route uses a dedicated first-party consumer-search key and does not read the local index.

```text
PRAXY_JOBS_KEY ─ search-praxy CLI / search_praxy_jobs MCP ─ HTTPS Praxy Jobs API
                         └─ one response page; no SQLite import or local REST proxy

anonymous browser ─ web/ same-origin search route ─ first-party consumer-search API
                      └─ server-only key and shared request budget

JSON snapshot ─────────┐
                       ├─ explicit CLI import ─ validation ─ SQLite jobs + FTS5 ─ REST API
Greenhouse board API ───┘                                  └─ source receipts      └─ local MCP tools
```

The live path calls a fixed PraxyJobs.com HTTPS endpoint with `X-API-Key`, disables redirects, bounds response size, and surfaces plan, cursor, and rate-limit errors without returning credential material. It requires your activated subscription and follows the [Praxy Jobs data license](https://praxyjobs.com/data-license). See [live-search usage](PRAXY_LIVE.md). It does not create a sync receipt, populate `/v1/jobs`, or turn a hosted API result into locally licensed data.

## Import contract

Each job needs a stable `source_id`, nonempty `title` and `company`, and an absolute HTTP(S) `source_url`. Optional fields are `location`, `work_mode` (`remote`, `hybrid`, `onsite`, or `unknown`), `description`, and an ISO 8601 `posted_at`. Leave unknown values blank or `null`; do not infer a posting date or remote eligibility from vague text. The [fictional feed](../examples/demo.json) is a complete example.

Imports are bounded to a 50 MiB JSON file or one streamed Greenhouse response, 10,000 jobs per source, 100,000 characters per description, and 20 million description characters per snapshot. `source_id` is capped at 200 characters; title, company, and location at 500 each; and `source_url` at 4,096. These limits are validation guardrails, not source-rights checks.

An import is a **complete snapshot of one source**. The importer validates every row, rejects duplicate IDs, and defaults to rejecting an empty snapshot. `--allow-empty` is an explicit instruction to close all active jobs for that source. A failed fetch or invalid item leaves the previous active set and receipts untouched.

`source` plus `source_id` is the stable identity; the public `job_…` ID is a deterministic hash of that pair. A successful import updates existing jobs and deactivates missing ones for that source only. `first_seen_at` survives reimports. `last_seen_at` is the last successful observation in the feed, not a live URL check. Search and detail return only active jobs.

## Receipts

Each successful snapshot creates a receipt in the same database transaction as the job changes. It records `source`, `import_kind`, `synced_at`, the SHA-256 digest of normalized snapshot data, input and active counts, and counts of new, updated, reopened, closed, and unchanged jobs. The digest is independent of feed row order. Receipts support repeatable import audits; they do **not** prove the source granted rights, that a listing is live, or that its apply URL works. See [source policy](SOURCE_POLICY.md).

When the CLI opens a database created by an earlier preview version, it initializes the receipt schema and backfills one `legacy` baseline record per existing source. This is migration metadata, **not** a newly accepted snapshot: only `source` and `active_count` are known; `synced_at`, `snapshot_sha256`, `input_count`, and historical change counts are `null`. Read-only API/MCP processes do not migrate old databases and may report the index unavailable until the CLI has opened it.

The read-only [`/v1/sources`](API_AND_MCP.md) endpoints and MCP source tools expose the latest receipt and history. They are observations of successful imports, not an uptime monitor or external validation service.

## Search and deployment

SQLite FTS5 indexes title, company, location, and description. Queries are tokenized and matched against active jobs, with optional location/company/work-mode filters and pagination. The API returns JSON and OpenAPI at `/docs`; the MCP server is local stdio. Both use `OPENJOBS_DB`, defaulting to `data/jobs.sqlite` relative to their working directory.

The included Docker Compose file binds the API to host loopback. `/health` reports process liveness; `/ready` requires a readable, initialized index and reports source and active-job counts, which may both be zero. No authentication, rate limiting, scheduler, background crawler, or remote MCP endpoint is included. A public service needs a rights-cleared feed, abuse controls, logs that avoid sensitive data, backup and removal procedures, and an independently verified deployment. See the [release checklist](RELEASE_CHECKLIST.md) and [security notes](../SECURITY.md).

## Public search website in development

The planned `openjobs.praxyjobs.com` website is a third, separate entry point for **anonymous people**. Its [source and local setup](../web/README.md) are in this repository's `web/` app. Its server-side search route calls a fixed Praxy Jobs consumer-search endpoint with a dedicated persisted `OPENJOBS_CONSUMER_SEARCH_KEY` (`key_kind=consumer`, `account_id=praxy-web`, `channel=candidate-search`); the browser must never receive that credential. The route validates query and filter bounds, applies shared per-visitor and global Redis request budgets, sets an upstream timeout, and returns only bounded job-card fields and original HTTPS apply URLs. The site does not import the hosted catalogue into the local SQLite index or turn a human browse session into a paid developer API key.

The web app's dedicated production consumer key, DNS, and real search were **not deployed or verified** on October 22, 2026. At this check, `praxyjobs.com/openjobs` returned 404 and `openjobs.praxyjobs.com` did not resolve. The existing [praxy.me/jobs](https://praxy.me/jobs) is a separate working consumer search. Keep the public README and release claims tied to the actual site deployment and code snapshot, not a build or this design. The [source policy](SOURCE_POLICY.md) covers first-party display rights and provenance.
