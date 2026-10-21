# OpenJobs web

The public search site in this repository. It browses real listings from the [Praxy Jobs](https://praxyjobs.com) consumer search API and sends people to each original HTTPS application. The browser never receives an API key. There are no bundled job records or sample listings in production.

## Run locally

Requires Node 22+, shared Redis, and a distinct, active Praxy Jobs first-party consumer key. Provision that persisted key only after the production consumer-search API accepts consumer-kind credentials. Its scope must be `key_kind=consumer`, `account_id=praxy-web`, and `channel=candidate-search`. The paid developer API uses `key_kind=service` keys; those keys, the existing landing-site key, and developer `PRAXY_JOBS_KEY` values must not be used for this anonymous site.

```bash
cd web
npm ci
cp .env.example .env.local
# Add OPENJOBS_CONSUMER_SEARCH_KEY and OPENJOBS_REDIS_URL to .env.local.
# Set OPENJOBS_PUBLIC_LAUNCH_ENABLED=1 only for the environment you are testing.
npm run dev
```

Open `http://localhost:3000`. Without the key or Redis, `/api/search` responds with a generic 503 and never calls upstream. With the launch flag off, the homepage and `/api/search` return 404. `GET /api/health` returns 200 only when the key exists and Redis responds, even before the launch flag is enabled.

To preview the production build locally, run `npm run build && npm run start`. The start script copies Next's static assets into the standalone output before starting the server.

## Production

Build from `web/Dockerfile` and expose port 3000. The proposed canonical hostname is `openjobs.praxyjobs.com`; add DNS only after the deployment responds correctly. Set:

| Variable | Purpose |
| --- | --- |
| `OPENJOBS_CONSUMER_SEARCH_KEY` | Server-only, persisted first-party consumer key with `key_kind=consumer`, `account_id=praxy-web`, and `channel=candidate-search`. Required for public launch; never use a paid service key or the existing landing-site key. |
| `OPENJOBS_REDIS_URL` | Shared Redis URL across all web replicas; required. |
| `OPENJOBS_GLOBAL_LIMIT_PER_MINUTE` | Upstream-protection cap. Defaults to 60; maximum 420. Keep the conservative default until observed traffic and upstream capacity justify a change. |
| `OPENJOBS_GLOBAL_LIMIT_PER_DAY` | Shared cap on upstream cache misses per UTC day. Defaults to 5,000; clamped to 1–20,000. Tune after observing real traffic and upstream capacity. |
| `OPENJOBS_PUBLIC_LAUNCH_ENABLED` | Set to `1` after health and a real search pass. Defaults off. |
| `PUBLIC_SITE_URL` | Verified HTTPS site origin, such as `https://openjobs.praxyjobs.com/`. If unset, canonical URL is omitted and pages are `noindex`. Preview domains remain `noindex` even when set. Set the branded origin only after live search passes. |

Use a trusted edge that **overwrites `X-Real-IP`** with the actual visitor IP. Railway's edge provides this header. Missing/invalid IPs share one conservative visitor bucket. Redis atomically enforces 25 requests per visitor per minute and 300 per UTC day; cache misses also count against shared 60/minute and 5,000/day upstream caps by default. Redis holds each bounded search response for 20 seconds. A Redis failure fails closed.

The server only calls `https://praxyjobs.com/v1/internal/consumer/jobs/search` with allowlisted `q`, `country`, `remote`, and a fixed 24-result limit. The homepage starts with an `engineer` search in India, a live-tested query; all searches require text to avoid an expensive unfiltered scan. Visitors can edit the role and choose any country. Current keyword searches return a selection of up to 24 matches without a continuation cursor; the page offers a link to continue on Praxy. If upstream supplies a cursor for a query, short-lived Redis page tokens bind it to the filters and allow up to four pages (96 jobs). Callers cannot submit raw upstream cursors. The upstream request has an 8-second timeout, rejects redirects, and caps response JSON at 1 MB. The public response contains only card fields needed for search. The source label is the original application hostname, not an unsupported claim about a specific ATS or a live URL check. `first_seen` is labeled as first seen by Praxy Jobs, not verified still open.

The public website's data display is governed by the [Praxy Jobs data license](https://praxyjobs.com/data-license); this repository's MIT license applies to code. Do not mirror the full job corpus or expose the consumer key.

## Verify

```bash
cd web
npm ci
npm run lint
npm run test
npm run typecheck
npm run build
docker build -t openjobs-web .
```

After the scoped consumer key is verified against the production consumer-search API, deploy and verify `/api/health`, a real search, an original application link, a second page when a cursor exists, rate limiting, and the off-flag 404 behavior before adding the public DNS record. An HTTP 200 alone does not prove the search capability works.
