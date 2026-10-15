"""Structured contracts for executable API tests and tool execution reports."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_serializer,
    model_validator,
)

from .security.redaction import redact_sensitive


HttpMethod = Literal["GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"]


class JsonAssertion(BaseModel):
    """A bounded JSON Pointer assertion, never executable expressions."""

    model_config = ConfigDict(extra="forbid")
    path: str = Field(default="", max_length=500)
    op: Literal["exists", "type", "eq", "ne", "length", "min", "max"]
    expected: Any = None

    @field_validator("path")
    @classmethod
    def validate_pointer(cls, value: str) -> str:
        import re

        if value and (not value.startswith("/") or re.search(r"~(?![01])", value)):
            raise ValueError("断言路径必须使用 JSON Pointer，如 /data/items/0/name")
        return value

    @model_validator(mode="after")
    def validate_expected(self):
        value = self.expected
        if self.op == "type" and value not in (
            "object",
            "array",
            "string",
            "integer",
            "number",
            "boolean",
            "null",
        ):
            raise ValueError("type 断言需要 JSON 类型名称")
        if self.op == "exists" and value is not None and not isinstance(value, bool):
            raise ValueError("exists 断言需要布尔值")
        if self.op == "length" and (type(value) is not int or value < 0):
            raise ValueError("length 断言需要非负整数")
        if self.op in {"min", "max"}:
            import math

            if type(value) not in (int, float) or not math.isfinite(value):
                raise ValueError("边界断言需要有限数值")
        return self


class HttpTestSpec(BaseModel):
    """One executable HTTP API test produced by the execution planner."""

    case_id: str
    name: str
    method: HttpMethod = "GET"
    path: str
    data_id: str | None = None
    source: str | None = None
    assertions: list[JsonAssertion] = Field(default_factory=list, max_length=50)
    headers: dict[str, str] = Field(default_factory=dict)
    query: dict[str, Any] = Field(default_factory=dict)
    json_body: Any | None = None
    json_body_present: bool = False
    expected_status: int = Field(default=200, ge=100, le=599)
    expected_json_contains: dict[str, Any] = Field(default_factory=dict)
    expected_json_schema: dict[str, Any] | None = None
    expected_text_contains: list[str] = Field(default_factory=list)

    @field_validator("method", mode="before")
    @classmethod
    def normalize_method(cls, value: str) -> str:
        return str(value).upper()

    @field_validator("path")
    @classmethod
    def validate_path(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("HTTP 测试 path 不能为空")
        if not value.startswith("/"):
            raise ValueError("HTTP 测试 path 必须以 / 开头")
        if "://" in value:
            raise ValueError("HTTP 测试 path 仅允许相对路径，目标主机由 base_url 指定")
        return value


class ExecutionConfig(BaseModel):
    """Controls whether and how generated tests are executed."""

    enabled: bool = False
    base_url: str = ""
    request_timeout_seconds: float = Field(default=8.0, ge=0.5, le=60.0)
    pytest_timeout_seconds: int = Field(default=30, ge=5, le=180)
    max_executable_cases: int = Field(default=6, ge=1, le=20)
    verify_tls: bool = True
    run_http_tool: bool = True
    run_pytest: bool = True
    use_llm_planner: bool = True
    use_llm_failure_analysis: bool = True
    mock_isolation: bool = False
    mock_seed: list[dict[str, Any]] = Field(default_factory=list, max_length=20)
    api_specs: list[HttpTestSpec] = Field(default_factory=list)

    @field_validator("base_url")
    @classmethod
    def normalize_base_url(cls, value: str) -> str:
        value = value.strip().rstrip("/")
        if value and not value.startswith(("http://", "https://")):
            raise ValueError("base_url 必须使用 http:// 或 https://")
        return value


class _PublicOutput(BaseModel):
    @field_validator("*", mode="after")
    @classmethod
    def redact_output_field(cls, value: Any) -> Any:
        return redact_sensitive(value)

    @model_serializer(mode="wrap")
    def redact_output(self, handler):
        return redact_sensitive(handler(self))


class AssertionOutcome(_PublicOutput):
    assertion_id: str
    kind: str
    path: str = ""
    passed: bool
    expected: Any = None
    actual: Any = None
    message: str = ""


class HttpExecutionResult(_PublicOutput):
    case_id: str
    name: str
    method: str
    url: str
    passed: bool
    status_code: int | None = None
    expected_status: int
    duration_ms: float | None = None
    failures: list[str] = Field(default_factory=list)
    data_id: str | None = None
    source: str | None = None
    executor: str = "http"
    execution_mode: str = "live"
    request: dict[str, Any] = Field(default_factory=dict)
    assertions: list[AssertionOutcome] = Field(default_factory=list)
    response_excerpt: str = ""
    response_content_type: str | None = None
    validation_error: str | None = None
    timed_out: bool = False
    error: str | None = None


class PytestExecutionResult(_PublicOutput):
    passed: bool
    exit_code: int
    duration_ms: float
    passed_count: int = 0
    failed_count: int = 0
    error_count: int = 0
    stdout: str = ""
    stderr: str = ""
    generated_test_file: str | None = None
    case_results: list[HttpExecutionResult] = Field(default_factory=list)


class FailureAnalysis(_PublicOutput):
    case_id: str
    category: Literal[
        "connectivity",
        "timeout",
        "authentication",
        "route_or_test_data",
        "server_error",
        "contract_mismatch",
        "assertion_failure",
        "unknown",
    ]
    probable_cause: str
    evidence: list[str] = Field(default_factory=list)
    suggestion: str = ""


class ToolInvocation(_PublicOutput):
    tool_name: Literal["http_api_test", "pytest_runner"]
    case_id: str
    arguments: dict[str, Any] = Field(default_factory=dict)


class ExecutionReport(_PublicOutput):
    enabled: bool = True
    planner_mode: str = "deterministic"
    executable_cases: list[HttpTestSpec] = Field(default_factory=list)
    tool_calls: list[ToolInvocation] = Field(default_factory=list)
    http_results: list[HttpExecutionResult] = Field(default_factory=list)
    pytest_result: PytestExecutionResult | None = None
    failure_analysis: list[FailureAnalysis] = Field(default_factory=list)
    summary: dict[str, Any] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    trace_id: str | None = None
    diagnostic_evidence: list[dict[str, Any]] = Field(default_factory=list)
    lifecycle: dict[str, Any] = Field(default_factory=dict)
    evidence_collection_overhead_ms: float = 0.0
    failure_analysis_v2: dict[str, Any] = Field(default_factory=dict)


def request_body_kwargs(body: Any, present: bool = False) -> dict[str, Any]:
    """Preserve legacy absent-body behavior while allowing an explicit JSON null."""
    if body is None and present:
        return {"content": "null"}
    return {"json": body}
