# Source and data policy

OpenJobs supports a direct Praxy Jobs API search with your key and a separate local index for a feed you may use. Its MIT license covers the code in this repository, **not** job postings supplied by another party. A public endpoint, a working API call, and an open-source client are not evidence that you may republish returned data.

## Planned public OpenJobs search

The proposed `openjobs.praxyjobs.com` website is a **first-party display** of selected Praxy Jobs results. Its server should call a fixed Praxy consumer-search endpoint with a dedicated server-held credential and return bounded job cards to an anonymous browser. It should not send the credential, full provider response, or bulk catalogue to the client. This route is still under development; the existing [Praxy consumer search](https://praxy.me/jobs) is a separate live site.

First-party display must still follow the [Praxy Jobs data license](https://praxyjobs.com/data-license): show the employer and original posting link, preserve source provenance, label observation times accurately, avoid claiming that every apply link is live, and handle removal or expiry signals. Do not assume the public site grants a downstream right to mirror or resell the corpus. If descriptions are displayed, respect employer ownership and the license's attribution requirements. Production service-key activation, request budgets, and removal handling are release gates, not permissions supplied by this document.

## Direct Praxy Jobs search

`search-praxy` and the `search_praxy_jobs` MCP tool send one keyed request to PraxyJobs.com and return a page to the caller. They do **not** import or persist the page in OpenJobs' SQLite index, create a local receipt, or make the jobs available through OpenJobs' REST API. Your `PRAXY_JOBS_KEY` comes from an [activated subscription](https://praxyjobs.com/docs/quickstart) and should stay in your environment or secret manager.

The [Praxy Jobs data license](https://praxyjobs.com/data-license) governs live results. As published on October 22, 2026, it permits use, storage, processing, and display in your own products while the subscription is active, requires provenance to remain attached, and restricts reselling raw API access or systematic redistribution as a competing dataset. Employer descriptions remain the employer's intellectual property; when displaying them, link to the original posting and identify the employer. If your downstream system stores results, it must handle removal or expiry signals within the license's **seven-day** window. OpenJobs' direct one-page search does not implement a downstream removal worker for you. Recheck the current license before launching a product on the data.

## Before importing a real source

Record the decision for each source outside the repository if it contains a contract or private contact details:

| Question | Evidence to record |
| --- | --- |
| Who controls the feed? | Owner, endpoint, and contact or published terms. |
| What use is permitted? | Indexing, storage, public display, API/MCP redistribution, and commercial use considered separately. |
| What must be shown? | Attribution, original apply link, branding, or other display requirements. |
| How is the feed kept current? | Refresh interval, pagination/completeness rules, deletion signal, and rate limits. |
| What happens when access ends? | Retention limit, deletion route, and who will act on a removal request. |
| Who approved this use? | Named reviewer, date, and a link to the governing terms or written permission. |

If permission is unclear, use the [fictional sample](../examples/demo.json) and keep the real feed out of demos and releases. The built-in Greenhouse adapter only fixes the fetch target and requires an explicit rights confirmation; it does not grant rights to a board's postings.

**Do not seed OpenJobs or the hosted Praxy Jobs API from FreeHire's keyless endpoint.** As of October 22, 2026, FreeHire's [data terms](https://freehire.me/terms) distinguish its MIT-licensed code from its hosted job data. Its [API plan](https://freehire.me/jobs-api) specifies when postings may be stored and displayed in a product, and limits redistribution as a raw feed. Recheck the terms before any integration; a licensed integration still needs its own source review and retention process.

## What a receipt proves

A **successful new-import** receipt records the snapshot OpenJobs accepted: source key, import kind, observation time, SHA-256 of the normalized snapshot, and new, updated, reopened, closed, and unchanged counts. The digest is useful for detecting whether two imports had the same normalized content. It is **not** a signature from the source, proof of permission, evidence that an apply link works, or proof that a job is still open.

An older preview database upgraded by the CLI gets a `legacy` baseline record. It is migration metadata, **not** evidence of a new successful import. Its active count is known, but observation time, digest, input count, and historical change counts are `null`, not zero, because those facts cannot be reconstructed.

`first_seen_at` and `last_seen_at` are OpenJobs observation times. `posted_at` comes from the source when provided. Do not label any of them as a verified posting or closing date. A successful complete snapshot can deactivate missing jobs; a failed or incomplete fetch must leave the prior active set intact. Empty snapshots need deliberate review because they close every active job for that source.

## Public demo and removal

Before showing real postings on PraxyJobs.com or another public surface:

1. Complete the source review above and use a feed whose permitted scope includes public display and the API/MCP access you expose.
2. Verify a sample of source and apply URLs manually. Mark any broken or redirected links as observations; OpenJobs does not check them automatically.
3. Identify how to remove a source and its stored records, including database backups and caches, if the owner withdraws permission. The repository does not yet automate erasure across backups.
4. Keep candidate data, resumes, credentials, cookies, signed or token-bearing source URLs, and private Praxy production data out of the feed and Git history. REST and MCP return the imported `source_url` verbatim.
5. Tell demo users which dataset they are seeing, when it was last imported, and what has **not** been verified.

Descriptions and links are untrusted external content. Applications and agents consuming them should render or quote them as data, not execute instructions embedded in a posting. See [security](../SECURITY.md) before exposing an instance publicly.
