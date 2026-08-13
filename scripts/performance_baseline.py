#!/usr/bin/env python3
"""Reproducible HTTP performance baseline for a running Req2Test stack.

This intentionally uses only the project's existing httpx dependency. It measures
the public API without retries so that every reported error is a real observation.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import math
import platform
import sys
import time
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Awaitable, Callable

import httpx


TERMINAL_STATUSES = {"completed", "failed"}


@dataclass
class Measurement:
    scenario: str
    concurrency: int
    requests: int
    successful_requests: int
    errors: int
    error_rate_percent: float
    throughput_requests_per_second: float
    average_latency_ms: float
    p95_latency_ms: float
    total_test_time_seconds: float
    status_codes: dict[str, int]


def percentile(values: list[float], percentile_value: float) -> float:
    """Return a nearest-rank percentile without a third-party statistics package."""
    if not values:
        return 0.0
    ordered = sorted(values)
    index = max(0, math.ceil(percentile_value * len(ordered)) - 1)
    return ordered[index]


async def measure_requests(
    *,
    scenario: str,
    concurrency: int,
    request_count: int,
    request: Callable[[int], Awaitable[httpx.Response]],
    success_status: int,
) -> tuple[Measurement, list[dict[str, Any]]]:
    semaphore = asyncio.Semaphore(concurrency)
    latencies_ms: list[float] = []
    statuses: dict[str, int] = {}
    successes: list[dict[str, Any]] = []
    errors = 0

    async def run_one(index: int) -> None:
        nonlocal errors
        async with semaphore:
            started = time.perf_counter()
            try:
                response = await request(index)
                elapsed_ms = (time.perf_counter() - started) * 1000
                latencies_ms.append(elapsed_ms)
                status_key = str(response.status_code)
                statuses[status_key] = statuses.get(status_key, 0) + 1
                if response.status_code == success_status:
                    try:
                        successes.append(response.json())
                    except ValueError:
                        errors += 1
                else:
                    errors += 1
            except httpx.HTTPError as exc:
                elapsed_ms = (time.perf_counter() - started) * 1000
                latencies_ms.append(elapsed_ms)
                error_key = type(exc).__name__
                statuses[error_key] = statuses.get(error_key, 0) + 1
                errors += 1

    started = time.perf_counter()
    await asyncio.gather(*(run_one(index) for index in range(request_count)))
    duration = time.perf_counter() - started
    successful_requests = request_count - errors
    measurement = Measurement(
        scenario=scenario,
        concurrency=concurrency,
        requests=request_count,
        successful_requests=successful_requests,
        errors=errors,
        error_rate_percent=round((errors / request_count) * 100, 3),
        throughput_requests_per_second=round(request_count / duration, 2),
        average_latency_ms=round(sum(latencies_ms) / len(latencies_ms), 2),
        p95_latency_ms=round(percentile(latencies_ms, 0.95), 2),
        total_test_time_seconds=round(duration, 3),
        status_codes=statuses,
    )
    return measurement, successes


def task_payload(run_id: str, index: int) -> dict[str, Any]:
    return {
        "title": f"PERF-{run_id}-{index:04d}",
        "requirement_text": (
            "性能基线任务：用户使用有效账号密码登录后，应成功进入系统首页。"
            f" 基线标识 {run_id}-{index}."
        ),
        "llm_settings": {"mode": "demo", "model": "gpt-4.1-mini"},
        "generation_config": {
            "include_positive": True,
            "include_negative": False,
            "include_edge": False,
            "max_cases": 1,
            "min_review_score": 85,
            "max_review_iterations": 0,
        },
        "execution_config": {"enabled": False},
    }


async def wait_for_terminal(
    client: httpx.AsyncClient,
    task_id: str,
    timeout_seconds: float,
) -> dict[str, Any]:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        response = await client.get(f"/api/v1/tasks/{task_id}")
        response.raise_for_status()
        state = response.json()
        if state.get("status") in TERMINAL_STATUSES:
            return state
        await asyncio.sleep(0.5)
    raise TimeoutError(f"Task {task_id} did not reach a terminal state")


async def run(args: argparse.Namespace) -> dict[str, Any]:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    run_id = f"{timestamp}-{uuid.uuid4().hex[:8]}"
    limits = httpx.Limits(
        max_connections=max(args.concurrency),
        max_keepalive_connections=max(args.concurrency),
    )
    timeout = httpx.Timeout(args.request_timeout)
    async with httpx.AsyncClient(
        base_url=args.base_url.rstrip("/"), limits=limits, timeout=timeout
    ) as client:
        health_before = {
            "health": (await client.get("/health")).status_code,
            "ready": (await client.get("/ready")).status_code,
        }

        email = f"perf-{run_id.lower()}@example.test"
        password = f"Perf-{uuid.uuid4().hex}!"
        register = await client.post(
            "/api/v1/auth/register", json={"email": email, "password": password}
        )
        register.raise_for_status()
        login = await client.post(
            "/api/v1/auth/login", json={"email": email, "password": password}
        )
        login.raise_for_status()
        token = login.json()["access_token"]
        client.headers["Authorization"] = f"Bearer {token}"

        seed_response = await client.post(
            "/api/v1/tasks", json=task_payload(run_id, -1)
        )
        seed_response.raise_for_status()
        seed_id = seed_response.json()["task_id"]
        seed_state = await wait_for_terminal(client, seed_id, args.drain_timeout)

        measurements: list[Measurement] = []
        for concurrency in args.concurrency:
            request_count = max(args.min_query_requests, concurrency * args.query_multiplier)
            measurement, _ = await measure_requests(
                scenario="task_status_result_query",
                concurrency=concurrency,
                request_count=request_count,
                request=lambda _index: client.get(f"/api/v1/tasks/{seed_id}"),
                success_status=200,
            )
            measurements.append(measurement)
            await asyncio.sleep(args.cooldown)

        submitted_task_ids: list[str] = []
        submission_index = 0
        for concurrency in args.concurrency:
            request_count = max(args.min_submit_requests, concurrency * args.submit_multiplier)
            offset = submission_index
            measurement, responses = await measure_requests(
                scenario="task_submission",
                concurrency=concurrency,
                request_count=request_count,
                request=lambda index, offset=offset: client.post(
                    "/api/v1/tasks", json=task_payload(run_id, offset + index)
                ),
                success_status=202,
            )
            measurements.append(measurement)
            submitted_task_ids.extend(
                response["task_id"] for response in responses if response.get("task_id")
            )
            submission_index += request_count
            await asyncio.sleep(args.cooldown)

        unique_task_ids = set(submitted_task_ids)
        drain = {
            "submitted_task_ids": len(submitted_task_ids),
            "unique_task_ids": len(unique_task_ids),
            "duplicate_response_task_ids": len(submitted_task_ids) - len(unique_task_ids),
            "terminal_tasks": 0,
            "completed_tasks": 0,
            "failed_tasks": 0,
            "timed_out": False,
        }
        deadline = time.monotonic() + args.drain_timeout
        remaining = set(unique_task_ids)
        while remaining and time.monotonic() < deadline:
            for task_id in list(remaining):
                response = await client.get(f"/api/v1/tasks/{task_id}")
                if response.status_code != 200:
                    continue
                status = response.json().get("status")
                if status in TERMINAL_STATUSES:
                    remaining.remove(task_id)
                    drain["terminal_tasks"] += 1
                    drain[f"{status}_tasks"] += 1
            if remaining:
                await asyncio.sleep(1)
        drain["timed_out"] = bool(remaining)
        drain["non_terminal_task_ids"] = sorted(remaining)

        health_after = {
            "health": (await client.get("/health")).status_code,
            "ready": (await client.get("/ready")).status_code,
        }

    return {
        "run_id": run_id,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "environment": {
            "base_url": args.base_url,
            "python": platform.python_version(),
            "platform": platform.platform(),
            "httpx": httpx.__version__,
        },
        "configuration": {
            "concurrency_levels": args.concurrency,
            "min_submit_requests": args.min_submit_requests,
            "submit_multiplier": args.submit_multiplier,
            "min_query_requests": args.min_query_requests,
            "query_multiplier": args.query_multiplier,
            "request_timeout_seconds": args.request_timeout,
        },
        "health_before": health_before,
        "seed_task": {"task_id": seed_id, "status": seed_state.get("status")},
        "measurements": [asdict(measurement) for measurement in measurements],
        "drain": drain,
        "health_after": health_after,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--concurrency", nargs="+", type=int, default=[10, 30, 50])
    parser.add_argument("--min-submit-requests", type=int, default=30)
    parser.add_argument("--submit-multiplier", type=int, default=2)
    parser.add_argument("--min-query-requests", type=int, default=100)
    parser.add_argument("--query-multiplier", type=int, default=10)
    parser.add_argument("--request-timeout", type=float, default=45.0)
    parser.add_argument("--drain-timeout", type=float, default=600.0)
    parser.add_argument("--cooldown", type=float, default=2.0)
    parser.add_argument("--output", type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if any(value < 1 for value in args.concurrency):
        raise SystemExit("Concurrency values must be positive")
    try:
        result = asyncio.run(run(args))
    except (httpx.HTTPError, TimeoutError) as exc:
        print(f"Performance baseline failed: {exc}", file=sys.stderr)
        return 1
    rendered = json.dumps(result, ensure_ascii=False, indent=2)
    print(rendered)
    if args.output:
        args.output.write_text(rendered + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
