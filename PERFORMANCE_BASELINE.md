# Req2Test Performance Baseline

Baseline run: `20260813T095100Z-201b04a1` (2026-08-13 09:51 UTC)

## Purpose and scope

This is a small, reproducible local baseline, not a capacity claim. It exercises two public,
authenticated API paths without changing the application, worker, database, or broker:

1. `POST /api/v1/tasks` — PostgreSQL task creation, Redis live projection, and Celery/RabbitMQ dispatch.
2. `GET /api/v1/tasks/{task_id}` — status and completed-result retrieval through the normal PostgreSQL/Redis reconciliation path.

WebSocket load is intentionally excluded. Its progress-stream semantics and 0.5-second update cadence
need a separate long-lived-connection profile and are not directly comparable with request/response throughput.

## Test environment

- Host: Apple M5, 16 GiB RAM, macOS/Darwin arm64
- Runtime: Docker Desktop 29.7.2, Linux arm64 containers
- Load generator: Python 3.11.15, `asyncio` + existing `httpx` 0.28.1
- Measurement location: inside the API container, targeting `http://127.0.0.1:8000`
- API image: `req2test-agent:dev`; no explicit container CPU or memory limits
- Data services: PostgreSQL 16 Alpine, Redis 7 Alpine, RabbitMQ 3.13 Management
- Worker: Celery, concurrency 2; application demo mode
- Database connection settings: pool size 5, max overflow 10 (Compose defaults)
- Run model: one warm run per level, HTTP keep-alive enabled, no client retries, 2-second cooldown between levels

The in-container loopback placement minimizes host-network noise. These numbers should therefore be
compared only with later runs using the same placement and configuration; they do not represent remote-client latency.

## Workload

For result queries, a completed one-case task was created first and queried repeatedly. For submissions,
each request used a unique title and requirement, demo generation, one positive test case, and execution disabled.
The levels generated 30/60/100 submissions and 100/300/500 completed-result queries respectively.

## Results

### Task submission — `POST /api/v1/tasks`

| Concurrency | Requests | Success | Throughput | Average | p95 | Error rate | Duration |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 10 | 30 | 30 | 126.42 req/s | 73.10 ms | 154.30 ms | 0.00% | 0.237 s |
| 30 | 60 | 60 | 128.26 req/s | 194.40 ms | 358.68 ms | 0.00% | 0.468 s |
| 50 | 100 | 100 | 176.30 req/s | 221.73 ms | 430.21 ms | 0.00% | 0.567 s |

All successful submissions returned HTTP 202.

### Completed task status/result — `GET /api/v1/tasks/{task_id}`

| Concurrency | Requests | Success | Throughput | Average | p95 | Error rate | Duration |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 10 | 100 | 100 | 409.17 req/s | 23.46 ms | 55.82 ms | 0.00% | 0.244 s |
| 30 | 300 | 300 | 418.74 req/s | 68.77 ms | 177.70 ms | 0.00% | 0.716 s |
| 50 | 500 | 500 | 482.54 req/s | 97.97 ms | 168.75 ms | 0.00% | 1.036 s |

All successful queries returned HTTP 200.

## Reliability and integrity checks

- `/health` and `/ready`: HTTP 200 before and after the load run.
- PostgreSQL, Redis, and RabbitMQ: healthy; Redis `PING` and RabbitMQ diagnostics passed.
- Celery worker: responded to `inspect ping`; RabbitMQ `celery` queue ended at 0 ready / 0 unacknowledged.
- API and worker: remained running; no `ERROR`, `Exception`, or `Traceback` entries appeared in the run window.
- 190 measured submissions produced 190 unique API task IDs and all 190 reached `completed` (0 failed, 0 drain timeout).
- Including the completed query seed: 191 database Tasks, 191 distinct task IDs, 191 distinct Celery task IDs, and 191 TestCases.
- Duplicate `(task_id, case_id, version)` TestCases: 0.
- Duplicate Execution idempotency keys: 0. Executions created: 0, as execution was deliberately disabled for the submission-isolation scenario.

## Bottleneck observations

No failure or saturation boundary was reached at 50 concurrent clients. The clear trend is submission
queueing latency: p95 increased from 154.30 ms at concurrency 10 to 430.21 ms at concurrency 50, while
throughput grew less proportionally. This is consistent with the synchronous request path doing three
durability operations (PostgreSQL, Redis, and broker publication) and with the configured database pool,
but this run does not isolate one of those components as the cause.

Completed-result queries sustained 409–483 req/s without errors. Their average latency rose from 23.46 ms
to 97.97 ms at concurrency 50, showing normal contention. The 30-client p95 being slightly higher than the
50-client p95 is expected single-run scheduling variance and should not be treated as an improvement.

## Follow-up opportunities

- Repeat each level three to five times and report median plus variance before setting an SLO.
- Add a host-network run and a 5–10 minute steady-state run to separate network cost and detect resource drift.
- Profile the submission path per PostgreSQL commit, Redis projection, and broker publish before changing code.
- Add a separate WebSocket connection/ramp/soak profile if concurrent live viewers become a capacity concern.
- Add an execution-enabled worker-throughput baseline separately; mixing test execution into API admission would obscure both measurements.

## Reproduction

With the Docker stack already running and project dependencies available:

```bash
python scripts/performance_baseline.py \
  --base-url http://127.0.0.1:8000 \
  --concurrency 10 30 50 \
  --output /tmp/req2test_performance_baseline.json
```

When the host Python environment is not installed, copy the script into the existing API container and
run it there, as this baseline did. The script creates an isolated user and unique task titles, performs no
automatic request retries, waits for all submitted tasks to reach a terminal state, and writes raw JSON.
