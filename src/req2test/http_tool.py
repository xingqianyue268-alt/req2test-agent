"""HTTP API test tool used by the Req2Test execution layer."""

from __future__ import annotations

import json
import time
from typing import Any

from .execution_models import HttpExecutionResult, HttpTestSpec, request_body_kwargs
from .schema_assertions import schema_failures
from .security.execution import validate_execution_target
from .security.redaction import protect_http_logs, redact_text


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
        failures.append(f"{path} 值不一致")
    return failures


_validate_execution_target = validate_execution_target


class HttpApiTestTool:
    """Execute structured HTTP API checks against a caller-provided base URL."""

    name = "http_api_test"

    def __init__(self, base_url: str, timeout_seconds: float = 8.0, verify_tls: bool = True) -> None:
        self.base_url = _validate_execution_target(base_url.strip())
        self.timeout_seconds = timeout_seconds
        self.verify_tls = verify_tls

    def invoke(self, spec: HttpTestSpec) -> HttpExecutionResult:
        import httpx

        protect_http_logs()
        url = f"{self.base_url}{spec.path}"
        started = time.perf_counter()
        failures: list[str] = []
        response_excerpt = ""
        status_code: int | None = None

        try:
            with httpx.Client(
                timeout=self.timeout_seconds,
                verify=self.verify_tls,
                follow_redirects=False,
            ) as client:
                response = client.request(
                    spec.method,
                    url,
                    headers=({"Content-Type": "application/json", **spec.headers} if spec.json_body_present else spec.headers),
                    params=spec.query,
                    **request_body_kwargs(spec.json_body, spec.json_body_present),
                )
            duration_ms = round((time.perf_counter() - started) * 1000, 2)
            status_code = response.status_code
            response_excerpt = redact_text(response.text)[:1500]
            response_content_type = response.headers.get("content-type")

            if response.status_code != spec.expected_status:
                failures.append(
                    f"状态码不一致：期望 {spec.expected_status}，实际 {response.status_code}"
                )

            # FastAPI and many validation frameworks use 422 when the request
            # reaches the route but the body/query does not satisfy the declared
            # contract. Preserve that evidence so failure attribution can classify
            # it as a contract/test-data problem rather than a generic assertion.
            if response.status_code == 422 and spec.expected_status != 422:
                failures.append(
                    "请求数据校验未通过：可能缺少必填请求体/参数，或字段类型不符合接口契约"
                )

            if spec.expected_json_contains or spec.expected_json_schema is not None:
                try:
                    payload = response.json()
                except (json.JSONDecodeError, ValueError):
                    failures.append("响应不是有效 JSON，无法执行 JSON 包含断言")
                else:
                    if spec.expected_json_contains:
                        failures.extend(_json_contains(payload, spec.expected_json_contains))
                    if spec.expected_json_schema is not None:
                        try:
                            failures.extend(schema_failures(payload, spec.expected_json_schema))
                        except ValueError:
                            failures.append("响应 Schema 无效或包含禁止的引用")

            for expected_text in spec.expected_text_contains:
                if expected_text not in response.text:
                    failures.append("响应正文缺少期望文本")

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
                response_content_type=response_content_type,
                validation_error=response_excerpt if response.status_code == 422 else None,
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
                timed_out=True,
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
