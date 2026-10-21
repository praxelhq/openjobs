# Search Praxy Jobs live

OpenJobs can query the [Praxy Jobs Search API](https://praxyjobs.com/docs/api) directly from its CLI or local MCP server. This is the **hosted-data path**. It uses your own `PRAXY_JOBS_KEY` and does not import results into SQLite, create a local sync receipt, or make them available from OpenJobs' `/v1/jobs` endpoint. The local index path is documented separately in [API and MCP recipes](API_AND_MCP.md).

## Before the first request

Follow the official [Praxy Jobs quickstart](https://praxyjobs.com/docs/quickstart): choose a plan, wait for **activated** access, and save the revealed key in your own environment or secret manager as `PRAXY_JOBS_KEY`. Checkout completion alone is not activation. Keep the key out of Git, issue reports, shell history, recordings, URLs, and MCP configs you may share.

With that environment variable available to the process:

```bash
uv sync
uv run openjobs search-praxy 'data engineer' --country IN --limit 10
```

This sends one HTTPS request to `https://praxyjobs.com/v1/jobs/search` with the key in the `X-API-Key` header. It prints a normalized JSON page. No background sync or local database is required. Results depend on your plan and the hosted API's current data; this repository includes no key or live postings.

## Filters and pagination

| CLI option | Meaning |
| --- | --- |
| Positional `query` | Keyword query; omit for a filtered browse. |
| `--country IN,DE` | Comma-separated two-letter country codes. |
| `--city`, `--company`, `--source` | Narrow by city, company, or ATS source code. |
| `--remote only` or `--remote exclude` | Include only remote roles or exclude them. |
| `--status open` | `open` (default), `closed`, or `all`. |
| `--exclude-duplicates` | Request duplicate suppression from the hosted API. |
| `--include-description` | Include full description text when the API supplies it. |
| `--limit 1..100` | Jobs requested on this page; default 20. |
| `--cursor VALUE` | Opaque `next_cursor` returned by the previous page. |

The output envelope is `{provider, jobs, total_estimate, next_cursor, limit}`. Despite its name, `total_estimate` is the exact filtered count in the hosted API's repeatable-read search snapshot. Each normalized job has a `job_key`, `title`, `company`, `source_url`, `status`, `source`, `source_slug`, `first_seen_at`, `last_seen_at`, and `has_salary`. When supplied by the API, OpenJobs also preserves fields such as `locations`, `employment_type`, `salary_derived`, `taxonomy`, and ATS provenance; full `description_text` is returned only with `--include-description` or the MCP equivalent. `first_seen_at` and `last_seen_at` are provider observations, not promises that a link is live. Keep each job's original source URL and source attribution with any downstream display.

For the next page, pass `next_cursor` back unchanged:

```bash
uv run openjobs search-praxy 'data engineer' --country IN --limit 10 --cursor 'OPAQUE_CURSOR_FROM_PREVIOUS_PAGE'
```

There is no offset pagination on this hosted path. A stale cursor can produce an HTTP 409 error; restart without a cursor. Missing or inactive access can produce 401/402/403. On HTTP 429, respect the reported `Retry-After` before retrying. OpenJobs limits one hosted response to 10 MiB and does not automatically retry or harvest the whole catalogue.

## MCP tool

The local `openjobs-mcp` executable also exposes `search_praxy_jobs`. Give **that process** `PRAXY_JOBS_KEY` through your MCP client's environment or secret settings. The tool accepts `query`, `country`, `city`, `company`, `source`, `remote`, `status`, `exclude_duplicates`, `include_description`, `limit`, and `cursor`, and returns the same normalized page as the CLI. It calls the Praxy Jobs API when invoked; the five local index tools do not.

For example, ask your MCP client to call `search_praxy_jobs({"query":"data engineer","country":"IN","limit":10})`. This is a direct network request, so the client's tool-approval and data-sharing settings matter. Do not paste your key into a chat prompt or tool argument.

## Data rights

The [Praxy Jobs data license](https://praxyjobs.com/data-license) governs results returned by the hosted API. It grants use, storage, processing, and display in your own products while a subscription is active, with provenance, description attribution, removal, rate-limit, and anti-redistribution obligations. Employer job-description text remains the employer's intellectual property. If you store or display results outside OpenJobs, follow the current terms, keep the original apply link and employer identification, and act on removal signals within the stated period. The direct OpenJobs search path itself does **not** store the returned page.
