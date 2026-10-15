"""HTTP API test tool used by the Req2Test execution layer."""

from __future__ import annotations

import time

from .assertions import evaluate_response
from .execution_models import HttpExecutionResult, HttpTestSpec, request_body_kwargs
from .security.execution import validate_execution_target
from .security.redaction import protect_http_logs, redact_text

_validate_execution_target = validate_execution_target


class HttpApiTestTool:
    """Execute structured HTTP API checks against a caller-provided base URL."""

    name = "http_api_test"

    def __init__(
        self, base_url: str, timeout_seconds: float = 8.0, verify_tls: bool = True
    ) -> None:
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
                    headers=(
                        {"Content-Type": "application/json", **spec.headers}
                        if spec.json_body_present
                        else spec.headers
                    ),
                    params=spec.query,
                    **request_body_kwargs(spec.json_body, spec.json_body_present),
                )
            duration_ms = round((time.perf_counter() - started) * 1000, 2)
            status_code = response.status_code
            response_excerpt = redact_text(response.text)[:1500]
            response_content_type = response.headers.get("content-type")

            assertions = evaluate_response(spec, response)
            failures = [item.message for item in assertions if not item.passed]

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
                data_id=spec.data_id,
                source=spec.source,
                request={
                    "method": spec.method,
                    "path": spec.path,
                    "headers": spec.headers,
                    "query": spec.query,
                    "json_body": spec.json_body,
                },
                assertions=assertions,
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
                data_id=spec.data_id,
                source=spec.source,
                request={"headers": spec.headers, "query": spec.query, "json_body": spec.json_body},
                timed_out=True,
                error=f"{type(exc).__name__}: {exc}",
            )
        except (httpx.RequestError, httpx.InvalidURL, ValueError, TypeError) as exc:
            duration_ms = round((time.perf_counter() - started) * 1000, 2)
            return HttpExecutionResult(
                case_id=spec.case_id,
                name=spec.name,
                method=spec.method,
                url=url,
                passed=False,
                expected_status=spec.expected_status,
                duration_ms=duration_ms,
                data_id=spec.data_id,
                source=spec.source,
                request={"headers": spec.headers, "query": spec.query, "json_body": spec.json_body},
                failures=["HTTP 请求规格无效或未收到有效响应"],
                error=f"{type(exc).__name__}: 请求未完成",
            )

    def invoke_many(self, specs: list[HttpTestSpec]) -> list[HttpExecutionResult]:
        return [self.invoke(spec) for spec in specs]
