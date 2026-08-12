"""HTTP API test tool used by the Req2Test execution layer."""

from __future__ import annotations

import json
import os
import time
from typing import Any
from urllib.parse import urlparse

from .execution_models import HttpExecutionResult, HttpTestSpec


def _json_contains(actual: Any, expected: Any, path: str = "$") -> list[str]:
    """Return assertion failures when expected is not recursively contained in actual."""

    failures: list[str] = []
    if isinstance(expected, dict):
        if not isinstance(actual, dict):
            return [f"{path} 期望为对象，但实际为 {type(actual).__name__}"]
        for key, expected_value in expected.items():
            if key not in actual:
                failures.append(f"{path}.{key} 缺失")
                continue
            failures.extend(_json_contains(actual[key], expected_value, f"{path}.{key}"))
        return failures

    if isinstance(expected, list):
        if not isinstance(actual, list):
            return [f"{path} 期望为数组，但实际为 {type(actual).__name__}"]
        if len(actual) < len(expected):
            failures.append(f"{path} 数组长度不足：期望至少 {len(expected)}，实际 {len(actual)}")
            return failures
        for index, expected_value in enumerate(expected):
            failures.extend(_json_contains(actual[index], expected_value, f"{path}[{index}]"))
        return failures

    if actual != expected:
        failures.append(f"{path} 值不一致：期望 {expected!r}，实际 {actual!r}")
    return failures


def _validate_execution_target(base_url: str) -> str:
    """Restrict remote execution by default to reduce SSRF risk when API is deployed."""

    parsed = urlparse(base_url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError("HTTP Tool 的 base_url 必须是有效的 http:// 或 https:// 地址")
    if parsed.username or parsed.password:
        raise ValueError("base_url 不允许携带用户名或密码")

    allow_remote = os.getenv("REQ2TEST_ALLOW_REMOTE_EXECUTION", "false").lower() in {
        "1",
        "true",
        "yes",
    }
    configured = os.getenv(
        "REQ2TEST_EXECUTION_ALLOWED_HOSTS",
        "localhost,127.0.0.1,::1,api",
    )
    allowed_hosts = {item.strip().lower() for item in configured.split(",") if item.strip()}
    hostname = parsed.hostname.lower()
    if not allow_remote and hostname not in allowed_hosts:
        raise ValueError(
            f"目标主机 {hostname!r} 不在执行白名单中。"
            "如确需测试远程环境，请设置 REQ2TEST_ALLOW_REMOTE_EXECUTION=true，"
            "或将主机加入 REQ2TEST_EXECUTION_ALLOWED_HOSTS。"
        )
    return base_url.rstrip("/")


class HttpApiTestTool:
    """Execute structured HTTP API checks against a caller-provided base URL."""

    name = "http_api_test"

    def __init__(self, base_url: str, timeout_seconds: float = 8.0, verify_tls: bool = True) -> None:
        self.base_url = _validate_execution_target(base_url.strip())
        self.timeout_seconds = timeout_seconds
        self.verify_tls = verify_tls

    def invoke(self, spec: HttpTestSpec) -> HttpExecutionResult:
        import httpx

        url = f"{self.base_url}{spec.path}"
        started = time.perf_counter()
        failures: list[str] = []
        response_excerpt = ""
        status_code: int | None = None

        try:
            with httpx.Client(
                timeout=self.timeout_seconds,
                verify=self.verify_tls,
                follow_redirects=True,
            ) as client:
                response = client.request(
                    spec.method,
                    url,
                    headers=spec.headers,
                    params=spec.query,
                    json=spec.json_body,
                )
            duration_ms = round((time.perf_counter() - started) * 1000, 2)
            status_code = response.status_code
            response_excerpt = response.text[:1500]

            if response.status_code != spec.expected_status:
                failures.append(
                    f"状态码不一致：期望 {spec.expected_status}，实际 {response.status_code}"
                )

            # FastAPI and many validation frameworks use 422 when the request
            # reaches the route but the body/query does not satisfy the declared
            # contract. Preserve that evidence so failure attribution can classify
            # it as a contract/test-data problem rather than a generic assertion.
            if response.status_code == 422:
                failures.append(
                    "请求数据校验未通过：可能缺少必填请求体/参数，或字段类型不符合接口契约"
                )

            if spec.expected_json_contains:
                try:
                    payload = response.json()
                except (json.JSONDecodeError, ValueError):
                    failures.append("响应不是有效 JSON，无法执行 JSON 包含断言")
                else:
                    failures.extend(_json_contains(payload, spec.expected_json_contains))

            for expected_text in spec.expected_text_contains:
                if expected_text not in response.text:
                    failures.append(f"响应正文缺少期望文本：{expected_text}")

            return HttpExecutionResult(
                case_id=spec.case_id,
                name=spec.name,
                method=spec.method,
                url=url,
                passed=not failures,
                status_code=status_code,
                expected_status=spec.expected_status,
                duration_ms=duration_ms,
                failures=failures,
                response_excerpt=response_excerpt,
            )
        except httpx.TimeoutException as exc:
            duration_ms = round((time.perf_counter() - started) * 1000, 2)
            return HttpExecutionResult(
                case_id=spec.case_id,
                name=spec.name,
                method=spec.method,
                url=url,
                passed=False,
                expected_status=spec.expected_status,
                duration_ms=duration_ms,
                failures=["请求超时"],
                error=f"{type(exc).__name__}: {exc}",
            )
        except httpx.RequestError as exc:
            duration_ms = round((time.perf_counter() - started) * 1000, 2)
            return HttpExecutionResult(
                case_id=spec.case_id,
                name=spec.name,
                method=spec.method,
                url=url,
                passed=False,
                expected_status=spec.expected_status,
                duration_ms=duration_ms,
                failures=["HTTP 请求未成功发送或未收到有效响应"],
                error=f"{type(exc).__name__}: {exc}",
            )

    def invoke_many(self, specs: list[HttpTestSpec]) -> list[HttpExecutionResult]:
        return [self.invoke(spec) for spec in specs]
