# Release checklist

Use this before the OpenJobs code or search website is called public. Record evidence links beside each completed item; a checked box without a link is not release proof.

## Tested source candidate

- [ ] Fresh clone on a machine outside the build environment: `uv sync`, sample import, API query, and MCP tool call succeed. Record setup time and the commit tested.
- [ ] `uv run pytest -q` and Docker build/smoke checks pass at the release commit in CI.
- [ ] Sample jobs are clearly fictional in README, API responses, and any demo. No production catalogue or live count is implied.
- [ ] The same imported job, source URL, and observation fields appear through REST and MCP.
- [ ] Receipt counts and snapshot digest are reproduced by a successful reimport; invalid and failed imports preserve the earlier active set. A deliberate empty snapshot uses `--allow-empty`.
- [ ] API error, pagination, empty result, and malformed input behavior are documented and tested.
- [ ] Direct Praxy Jobs CLI/MCP search is checked against the documented contract; an authorized live-key smoke, if run, is recorded without exposing the key or hosted job descriptions in CI logs. Local sample tests do not count as live API proof.
- [ ] Dependencies are locked; no credentials, cookies, applicant data, internal endpoints, or unlicensed postings appear in tracked files or history.
- [ ] Designated technical and source-rights reviewers have **effective** repository access and can review the commit, not merely pending invitations.
- [ ] A maintainer records source-rights and public-deployment decisions. The fictional quickstart can be tested without a live-data grant; a real-data site cannot.

## Public repository decision

- [ ] Review **every commit**, tag, issue body, PR discussion, release asset, and workflow log for private strategy, people, tokens, URLs, and data. Internal planning documents and team assignments must not appear in published history. Deleting a committed file later still leaves it in earlier commits.
- [ ] When a private planning repository has committed internal material, export the reviewed release commit as a clean `git archive` snapshot, omit internal plans, owner notes, private issue links, and any staging-only artifacts that do not belong in the public package, inspect the resulting file list and content, then initialize a **new** public repository from it. Do not flip the private planning repository public; its old commits, issues, PR bodies, and Actions logs would remain discoverable.
- [ ] Publish only rights-cleared example data. Verify the license notices for code and media assets independently from any job-data permission.
- [ ] Check README links, install path, CLI output, API/MCP recipes, issue templates, security reporting, and contribution steps against the exact public commit.
- [ ] Give first-time users at least two bounded, reproducible contribution paths. Open Discussions only when a maintainer can respond.
- [ ] Tag and write a release note that states what works, what does not, migration implications, and the source commit. Use a real screenshot, video, or terminal recording only if it shows the released code and site state.
- [ ] State whether the public website source is in this repository, a linked public repository, or private. Do not call private website code open source because the CLI is MIT-licensed.

## Public website decision

A public GitHub repository, the existing Praxy Jobs API, and a public OpenJobs search website have separate verification gates. A verified repository may be published as a **developer preview** before the website is ready; do not announce the full OpenJobs product launch until both repository and real anonymous search pass. The existing [Praxy consumer search](https://praxy.me/jobs) is a useful interim route, but it is not verification of an OpenJobs deployment.

- [ ] An anonymous visitor can use the chosen PraxyJobs.com OpenJobs route to search **real** jobs without signing up or providing an API key, change filters, page, open a result, and follow its original employer/application link.
- [ ] Each result shows employer, source attribution, and a correctly labelled observation time. Empty, loading, error, stale-link, and removal states work on desktop and mobile. No description or live-link claim exceeds available evidence.
- [ ] A dedicated, active first-party service credential stays on the server; the search route has shared request and cost limits, bounded filters, safe logs, monitoring, and a rollback path. Test 401/402/429 and provider outage behavior without exposing a credential to the browser.
- [ ] The dataset's display, attribution, API/MCP, retention, and deletion rights are recorded in [source policy](SOURCE_POLICY.md). Removal signals have an owner and tested handling path.
- [ ] Verify the public site from a fresh anonymous session after production deployment. Record URL, commit, representative query, filter/pagination behavior, original-link destination, and a real screenshot.
- [ ] If a local-index API is also exposed publicly, separately verify `/ready` source and active-job counts, dataset rights, authentication or deliberate-public-access decision, rate limits, safe logs, backups, and removal procedure. The included Compose service is loopback only and does not satisfy this gate.

## Launch communication

- [ ] Lead with a real anonymous search → original source-link task on the verified public website. Present the CLI/MCP and fictional import demo as additional developer paths.
- [ ] Explain the OpenJobs website, Praxy Jobs hosted API, this open-source package, and praxy.me/jobs as distinct surfaces when their code or data boundaries differ.
- [ ] Ask outside job seekers and developers for specific task feedback. Measure searches, source-link clickthrough, and successful developer setup separately from GitHub stars; do not solicit artificial stars or votes.
- [ ] Make no superiority, scale, freshness, or “dead-link-free” claim without evidence from the released dataset and outside users.

This checklist is the gate for claims about a public release. Keep private project plans in a separate private location.
