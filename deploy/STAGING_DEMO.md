# Fictional-data staging demo

This deployment runs the OpenJobs code with **eight fictional jobs** from
[`examples/demo.json`](../examples/demo.json). It is a smoke-test service, not
the PraxyJobs.com hosted API, a live jobs feed, or a public launch.

## Local smoke test

The normal `openjobs` Compose service retains the manual import workflow in the
README. The separate `demo-stage` profile seeds a dedicated named SQLite volume:

```bash
docker compose --profile demo up --build -d demo-stage
curl -fsS http://127.0.0.1:8001/ready
curl -fsS http://127.0.0.1:8001/v1/sources
curl -fsS 'http://127.0.0.1:8001/v1/jobs?query=engineer'
docker compose --profile demo down
```

The loopback bind keeps the demo off the local network. `down` preserves the
volume. The next start validates the existing database and imports the packaged
fixture again; it refuses other sources, unknown job IDs, changed job content,
or receipt history with a different fixture digest. If the fixture changes in
a future release, use a **new demo volume** after reviewing its contents; do
not erase a shared or unknown volume. The demo startup requires
`OPENJOBS_DEMO_MODE=fictional` and the exact database path
`/app/data/jobs.sqlite` on a mounted volume. `/ready` checks that the index is
initialized and readable, including an intentionally empty index; the demo
smoke check must separately assert eight active jobs. The
packaged fixture must use company names marked `(demo)`, `example.com` links,
and no claimed posting dates.

## Railway staging setup

Use an **isolated staging environment** and a new service sourced from this
repository. Set the service to use the root `Dockerfile`, one replica, and:

| Setting | Value |
| --- | --- |
| Start command | `python /app/scripts/serve_demo.py` |
| Healthcheck path | `/ready` |
| Healthcheck timeout | `60` seconds |
| Volume mount | `/app/data` |
| `OPENJOBS_DB` | `/app/data/jobs.sqlite` |
| `OPENJOBS_DEMO_MODE` | `fictional` |
| `RAILWAY_RUN_UID` | `0` |

Railway mounts volumes owned by root. `RAILWAY_RUN_UID=0` lets the launcher set
ownership on `/app/data` and the three known SQLite files; it then drops to
UID/GID 10001 **before** importing the fixture or starting Uvicorn. Railway
supplies `PORT`; the launcher binds to that port. It fails if a Railway volume
is not mounted at `/app/data`.

Keep **public networking disabled**: do not generate a Railway domain or attach
the service to PraxyJobs.com yet. Railway's private network can reach the
service at `http://<service>.railway.internal:<PORT>`. Confirm `/ready` returns
200 with `indexed_jobs: 8`, `/v1/sources` reports `demo:fictional`, and search
returns only `example.com` source links and companies marked `(demo)`. Restart
the service and repeat those checks to verify volume persistence. Check that the
server process runs as UID 10001 after startup. Record the deployed Git commit
and the stage test results.

## Public exposure gate

This API has no built-in authentication or request limiting. Before adding a
public domain or site proxy, provide an ingress limit or access control,
document monitoring and rollback, take a volume backup, verify the exact
deployed commit, and label the dataset prominently as fictional. A real feed
requires separate rights for indexing, display, API access, retention, and
removal. Keep real listings and private Praxy data out of this demo volume.

The generic Docker image checks liveness at `/health`, so an intentionally empty
index is not marked as a crashed server. This demo's Compose and Railway checks
use `/ready` for index availability, then require `indexed_jobs: 8` in the smoke
check. Railway's deployment check does not replace ongoing uptime monitoring
after traffic is routed.
