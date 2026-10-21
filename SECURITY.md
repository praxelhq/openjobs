# Security

## Report a vulnerability privately

Email **[support@praxy.me](mailto:support@praxy.me?subject=OpenJobs%20security%20report)** with the subject `OpenJobs security report`. Include the affected version or commit, reproduction steps, impact, and whether a proof of concept contains sensitive data. If GitHub private vulnerability reporting is enabled for this repository, you may use its **Report a vulnerability** action instead.

Please do not put exploit details, credentials, or private feed data in a public issue or discussion. There is no bug-bounty program or promised response time in this preview.

## Current trust boundary

OpenJobs changes its **local index** only through explicit CLI imports. Its HTTP API and five local-index MCP tools are read-only. The separate `search-praxy` CLI command and `search_praxy_jobs` MCP tool make a direct HTTPS request to the fixed Praxy Jobs API with `PRAXY_JOBS_KEY`; they do not store results in SQLite. The Greenhouse importer accepts a board token and calls a fixed HTTPS host. Neither path fetches an arbitrary user-supplied URL. Job descriptions and source links are **untrusted content**. An agent or app consuming them must treat embedded instructions as job text, not as commands to follow.

Treat `PRAXY_JOBS_KEY` as a secret. Supply it to the CLI or MCP process through a private environment or secret manager. Do not paste it into prompts, add it to a shared MCP config, commit it to Git, place it in a URL, or include it in logs or recordings. The direct search path is subject to the [hosted API's subscription and data license](https://praxyjobs.com/data-license); using this MIT-licensed client does not grant access to the hosted dataset.

The project does not store applicant profiles or resumes, and it includes no telemetry or authentication. It **does** store whatever job text and URLs you import in a local SQLite file. Do not import credentials, signed URLs, token-bearing query strings, private applicant data, or listings whose display and retention rights you have not reviewed. The original `source_url` is returned through REST and MCP. Database files, backups, logs, and exported API results can expose the imported content.

## Deployment limits

The included Docker Compose service binds the API to host loopback. It is for local evaluation, not an internet-facing configuration. The API has no authentication or built-in rate limiting. `/health` checks that the process responds; `/ready` requires a readable, initialized index and reports source and active-job counts. It can return 200 with zero sources and zero active jobs. Neither endpoint verifies source rights, URL liveness, or data correctness.

Before exposing an instance beyond a trusted boundary, decide whether the dataset is deliberately public, add appropriate authentication and request limits, use TLS at the edge, restrict access to the database and backups, monitor errors without logging sensitive feed content, and define a source-removal and backup-retention procedure. Review the [source policy](docs/SOURCE_POLICY.md) and [release checklist](docs/RELEASE_CHECKLIST.md). A public API or remote MCP service is a separate deployment project.

## Planned anonymous search website

The proposed `openjobs.praxyjobs.com` app is a separate public-facing server, not this loopback SQLite API. Its `OPENJOBS_CONSUMER_SEARCH_KEY` must exist only in server secrets. The browser should call a same-origin bounded search route, never Praxy Jobs' privileged endpoint directly. Production readiness requires a dedicated active service key, shared per-visitor and global request budgets, bounded inputs and responses, upstream timeouts, safe error and log handling, TLS, monitoring, and a rollback path. Source attribution and removal obligations still apply to the displayed cards. Do not represent a draft or a link to [praxy.me/jobs](https://praxy.me/jobs) as a verified OpenJobs production deployment.
