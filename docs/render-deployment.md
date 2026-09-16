# Render Free + Neon

`render.yaml` provisions one Docker web service, using the repository Dockerfile,
`/health`, production cookies, demo generation and eager tasks/evaluations.
No Redis, RabbitMQ, persistent disk or independent worker is required.

## Provisioning

Deploy this branch as a Render Blueprint. The only external secrets are
`DATABASE_URL` and `DATABASE_URL_UNPOOLED` from the existing Neon project.
Render generates `JWT_SECRET_KEY`. An authorized deployment agent can supply
the database URLs; there is no need to configure the other variables manually.
Use a pooled Neon URL for normal traffic and the direct URL for migration.
For this small deployment, one direct URL can also be used in both fields.
Neither value belongs in Git. The application accepts `postgres://`,
`postgresql://`, and `postgresql+psycopg://`, preserving TLS query parameters
and URL-encoded credentials while selecting psycopg 3.

## Startup and storage

The Docker command runs `python -m req2test.deploy`. When
`REQ2TEST_AUTO_MIGRATE=true`, it obtains a PostgreSQL advisory lock, runs
`alembic upgrade head`, then initializes the knowledge catalog. Repeated starts
only apply pending revisions. It never stamps, downgrades or recreates the
database. A migration error prevents the web process from starting.

Render Free does not support paid pre-deploy jobs, so migration is part of
startup. Uvicorn listens on `0.0.0.0:$PORT` (8000 when unset), with one process.
Compose keeps its explicit API, migration and worker commands unchanged.

Chroma uses a fresh directory beneath `/tmp/req2test-chroma` per start. Built-in
knowledge and uploaded document source text live in PostgreSQL. The existing
idempotent seed service detects the empty index and reconstructs all catalog
documents. A Chroma initialization failure is logged without preventing login
or `/health`; an administrator can retry through the knowledge rebuild action.
No external embedding API or model download is required (hashing embeddings).

In-memory task projections are bounded to 100 entries and disposable. Completed
tasks/results and evaluations remain in PostgreSQL. Both eager flags are
required when selecting `REQ2TEST_TASK_STORE=memory`; do not use multiple web
processes or separate workers in this mode. An interrupted synchronous request
is not automatically resumed after a free-instance restart. `/ready` checks
PostgreSQL and the selected task store, without probing unused brokers.

The executable demo targets `127.0.0.1:$PORT` on the server. Compose retains
`http://api:8000`. Existing execution-host restrictions remain enabled.

## Validation

Run the full test suite against a **disposable local PostgreSQL database**:

```sh
DATABASE_URL=postgresql+psycopg://... python -m pytest -q
```

Never run database tests against production: fixtures use temporary schemas and
exercise downgrade/upgrade there. For a separate disposable deployment, run:

```sh
python scripts/smoke_render.py http://127.0.0.1:18000
```

The smoke script creates test data and verifies public pages, authentication,
secure cookies, authenticated workbench, knowledge retrieval, a real HTTP/Pytest
task, and an eager evaluation. Use the production Blueprint settings locally;
the script supplies the Secure cookie explicitly for HTTP-only localhost.

## Domain cutover and existing data

Keep Railway and current DNS unchanged until the Render public URL has passed
health, registration, task and evaluation checks. Then add `req2test.com` as a
custom domain in Render, obtain its exact DNS instructions, and update DNS only
after any required Railway data copy and verification. No domain is declared
in this Blueprint, so provisioning cannot move live traffic prematurely.

An empty Neon database does not contain existing Railway users/tasks. Database
schema initialization is not a historical-data migration. If Railway stores
data elsewhere, use a consistent source backup/import and verify row counts
before cutover; never overwrite a populated target blindly.

## Free-plan limitations

Render Free sleeps after inactivity and uses an ephemeral filesystem. Resource
limits can affect simultaneous generation/evaluation requests; this setup is
for a small demo, not a durable background job queue. A successful local run
does not prove the cloud memory limit: verify the actual Render deployment.

References: [Render Free](https://render.com/docs/free),
[Blueprint specification](https://render.com/docs/blueprint-spec),
[Docker deploy lifecycle](https://render.com/docs/deploys).
