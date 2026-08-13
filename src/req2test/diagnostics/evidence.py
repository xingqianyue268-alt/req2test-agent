"""Structured, bounded and sanitized evidence collection.

Collectors only record observable facts. Root-cause interpretation deliberately
lives in a separate Stage 2 classifier.
"""

from __future__ import annotations

import re
import time
import uuid
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any
from urllib.parse import urlparse

from pydantic import BaseModel, Field

from ..execution_models import HttpExecutionResult, HttpTestSpec, PytestExecutionResult


class EvidenceType(StrEnum):
    HTTP_REQUEST = "http_request"
    HTTP_RESPONSE = "http_response"
    ASSERTION = "assertion"
    PYTEST = "pytest"
    RAG_RETRIEVAL = "rag_retrieval"
    LLM_GENERATION = "llm_generation"
    WORKER_EXCEPTION = "worker_exception"
    INFRASTRUCTURE = "infrastructure"
    VALIDATION = "validation"
    TIMEOUT = "timeout"
    SYSTEM = "system"


class EvidenceSeverity(StrEnum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


class TraceContext(BaseModel):
    trace_id: str
    task_id: str
    celery_task_id: str | None = None
    case_id: str | None = None
    execution_id: str | None = None

    @classmethod
    def for_task(cls, task_id: str, celery_task_id: str | None = None) -> "TraceContext":
        # A business task is already a UUID and is the stable, non-log-derived
        # correlation root across FastAPI, Celery, tools and persistence.
        return cls(trace_id=task_id, task_id=task_id, celery_task_id=celery_task_id)

    def child(
        self, *, case_id: str | None = None, execution_id: str | None = None
    ) -> "TraceContext":
        return self.model_copy(
            update={"case_id": case_id, "execution_id": execution_id}
        )


_SECRET_KEYS = {
    "api_key",
    "apikey",
    "authorization",
    "cookie",
    "credential",
    "credentials",
    "client_secret",
    "password",
    "private_key",
    "proxy_authorization",
    "secret",
    "session",
    "set_cookie",
    "token",
    "x_api_key",
}
_SAFE_REQUEST_HEADERS = {"accept", "content-type", "user-agent", "x-request-id"}


def _normalized_key(value: str) -> str:
    return re.sub(r"[-\s]", "_", value.strip().lower())


def _redact_text(value: str) -> str:
    value = re.sub(r"(?i)bearer\s+[A-Za-z0-9._~+/=-]+", "Bearer ***", value)
    value = re.sub(r"://[^/@\s]+:[^/@\s]+@", "://***:***@", value)
    return re.sub(
        r"(?i)(api[_-]?key|authorization|cookie|client[_-]?secret|credential|"
        r"password|private[_-]?key|proxy[_-]?authorization|secret|session|token|"
        r"x[_-]?api[_-]?key)\s*[=:]\s*[^\s,;]+",
        r"\1=***",
        value,
    )


def sanitize_evidence(
    value: Any,
    *,
    key: str = "",
    text_limit: int = 4000,
    list_limit: int = 50,
) -> Any:
    """Recursively remove secrets and bound evidence before persistence."""

    if isinstance(value, dict):
        cleaned: dict[str, Any] = {}
        for item_key, item_value in value.items():
            normalized = _normalized_key(str(item_key))
            if normalized in _SECRET_KEYS or any(
                token in normalized
                for token in ("password", "secret", "private_key", "authorization")
            ):
                cleaned[str(item_key)] = "***"
            else:
                cleaned[str(item_key)] = sanitize_evidence(
                    item_value,
                    key=str(item_key),
                    text_limit=text_limit,
                    list_limit=list_limit,
                )
        return cleaned
    if isinstance(value, (list, tuple, set)):
        items = list(value)
        cleaned = [
            sanitize_evidence(item, key=key, text_limit=text_limit, list_limit=list_limit)
            for item in items[:list_limit]
        ]
        if len(items) > list_limit:
            cleaned.append(f"…[{len(items) - list_limit} items truncated]")
        return cleaned
    if isinstance(value, str):
        cleaned = _redact_text(value)
        limit = min(text_limit, 1500) if _normalized_key(key) in {
            "response_excerpt",
            "stdout_excerpt",
            "stderr_excerpt",
            "excerpt",
        } else text_limit
        return cleaned if len(cleaned) <= limit else cleaned[:limit] + "…[truncated]"
    return value


class FailureEvidence(BaseModel):
    evidence_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    trace_id: str
    task_id: str
    celery_task_id: str | None = None
    case_id: str | None = None
    execution_id: str | None = None
    stage: str
    evidence_type: EvidenceType
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    summary: str
    details: dict[str, Any] = Field(default_factory=dict)
    severity: EvidenceSeverity = EvidenceSeverity.INFO


class EvidenceCollector:
    """Accumulates sanitized facts under one immutable trace context."""

    def __init__(self, context: TraceContext) -> None:
        self.context = context
        self._items: list[FailureEvidence] = []
        self._overhead_seconds = 0.0

    @property
    def items(self) -> list[FailureEvidence]:
        return list(self._items)

    def add(
        self,
        evidence_type: EvidenceType,
        *,
        stage: str,
        summary: str,
        details: dict[str, Any] | None = None,
        severity: EvidenceSeverity = EvidenceSeverity.INFO,
        context: TraceContext | None = None,
    ) -> FailureEvidence:
        started = time.perf_counter()
        active = context or self.context
        item = FailureEvidence(
            trace_id=active.trace_id,
            task_id=active.task_id,
            celery_task_id=active.celery_task_id,
            case_id=active.case_id,
            execution_id=active.execution_id,
            stage=stage,
            evidence_type=evidence_type,
            summary=sanitize_evidence(summary, key="summary"),
            details=sanitize_evidence(details or {}),
            severity=severity,
        )
        self._items.append(item)
        self._overhead_seconds += time.perf_counter() - started
        return item

    def collect_http(self, spec: HttpTestSpec, result: HttpExecutionResult) -> None:
        context = self.context.child(case_id=spec.case_id, execution_id=spec.case_id)
        safe_headers = {
            key: value
            for key, value in spec.headers.items()
            if key.strip().lower() in _SAFE_REQUEST_HEADERS
        }
        self.add(
            EvidenceType.HTTP_REQUEST,
            stage="http_execution",
            summary=f"{spec.method} {spec.path}",
            details={
                "method": spec.method,
                "path": spec.path,
                "headers": safe_headers,
                "query_summary": spec.query,
                "body_summary": spec.json_body,
                "expected_status": spec.expected_status,
            },
            context=context,
        )
        response_details = {
            "method": result.method,
            "path": urlparse(result.url).path,
            "expected_status": result.expected_status,
            "actual_status": result.status_code,
            "duration_ms": result.duration_ms,
            "content_type": result.response_content_type,
            "response_excerpt": result.response_excerpt,
            "error": result.error,
        }
        self.add(
            EvidenceType.HTTP_RESPONSE,
            stage="http_execution",
            summary=(
                f"HTTP {result.status_code}" if result.status_code is not None else "No HTTP response"
            ),
            details=response_details,
            severity=EvidenceSeverity.INFO if result.passed else EvidenceSeverity.ERROR,
            context=context,
        )
        if result.failures:
            self.add(
                EvidenceType.ASSERTION,
                stage="http_assertion",
                summary="HTTP assertions did not match expected contract",
                details={"failures": result.failures},
                severity=EvidenceSeverity.ERROR,
                context=context,
            )
        if result.status_code == 422 and result.validation_error:
            self.add(
                EvidenceType.VALIDATION,
                stage="http_validation",
                summary="Request reached endpoint but failed validation",
                details={
                    "expected_status": result.expected_status,
                    "actual_status": result.status_code,
                    "validation_error": result.validation_error,
                    "suspected_contract_issue": True,
                },
                severity=EvidenceSeverity.ERROR,
                context=context,
            )
        if result.timed_out:
            self.add(
                EvidenceType.TIMEOUT,
                stage="http_execution",
                summary="Target did not respond before the configured timeout",
                details={"duration_ms": result.duration_ms, "error": result.error},
                severity=EvidenceSeverity.ERROR,
                context=context,
            )

    def collect_pytest(self, result: PytestExecutionResult) -> None:
        failed_nodes = re.findall(r"FAILED\s+([^\s]+)", result.stdout + "\n" + result.stderr)
        assertions = [
            line.strip()
            for line in (result.stdout + "\n" + result.stderr).splitlines()
            if "AssertionError" in line or line.lstrip().startswith("E       assert")
        ][:20]
        self.add(
            EvidenceType.PYTEST,
            stage="pytest",
            summary="Pytest suite passed" if result.passed else "Pytest suite failed",
            details={
                "exit_code": result.exit_code,
                "passed_count": result.passed_count,
                "failed_count": result.failed_count,
                "error_count": result.error_count,
                "duration_ms": result.duration_ms,
                "failed_node_ids": failed_nodes,
                "assertion_summary": assertions,
                "stdout_excerpt": result.stdout,
                "stderr_excerpt": result.stderr,
            },
            severity=EvidenceSeverity.INFO if result.passed else EvidenceSeverity.ERROR,
        )

    def collect_rag(self, *, query: str, top_k: int, contexts: list[Any]) -> None:
        results = []
        for index, context in enumerate(contexts):
            if isinstance(context, dict):
                results.append(
                    {
                        "document_id": context.get("document_id") or context.get("id"),
                        "source": context.get("source"),
                        "kind": context.get("kind"),
                        "distance": context.get("distance"),
                        "score": context.get("score"),
                        "excerpt": context.get("excerpt") or context.get("text"),
                    }
                )
            else:
                results.append(
                    {"document_id": None, "source": f"retrieval-{index + 1}", "excerpt": str(context)}
                )
        self.add(
            EvidenceType.RAG_RETRIEVAL,
            stage="rag_retrieval",
            summary=f"RAG returned {len(results)} of top {top_k} requested contexts",
            details={
                "query": query,
                "top_k": top_k,
                "returned_count": len(results),
                "results": results,
            },
            severity=EvidenceSeverity.WARNING if not results else EvidenceSeverity.INFO,
        )

    def collect_generation(
        self,
        *,
        provider: str,
        model: str | None,
        duration_ms: float,
        parse_success: bool,
        generated_case_count: int,
        validation_issues: list[str],
        review_score: int | None,
    ) -> None:
        self.add(
            EvidenceType.LLM_GENERATION,
            stage="test_generation",
            summary="Structured test generation completed" if parse_success else "Structured output parse failed",
            details={
                "provider": provider,
                "model": model,
                "duration_ms": duration_ms,
                "structured_output_parse_success": parse_success,
                "generated_case_count": generated_case_count,
                "validation_issues": validation_issues,
                "review_score": review_score,
            },
            severity=EvidenceSeverity.INFO if parse_success else EvidenceSeverity.ERROR,
        )

    def collect_worker(
        self,
        *,
        event: str,
        stage: str,
        retry_count: int = 0,
        exception: BaseException | None = None,
    ) -> None:
        self.add(
            EvidenceType.WORKER_EXCEPTION if exception else EvidenceType.SYSTEM,
            stage=stage,
            summary=f"Worker {event}",
            details={
                "event": event,
                "retry_count": retry_count,
                "exception_type": type(exception).__name__ if exception else None,
                "exception_summary": str(exception) if exception else None,
            },
            severity=EvidenceSeverity.ERROR if exception else EvidenceSeverity.INFO,
        )

    def collect_infrastructure(self, checks: dict[str, dict[str, Any] | str]) -> None:
        normalized = {}
        failing = False
        for name, state in checks.items():
            item = state if isinstance(state, dict) else {"state": state}
            normalized[name] = item
            if str(item.get("state", "unknown")).lower() in {"failed", "unavailable", "error"}:
                failing = True
        self.add(
            EvidenceType.INFRASTRUCTURE,
            stage="infrastructure",
            summary="Dependency state captured from explicit checks",
            details={"checks": normalized},
            severity=EvidenceSeverity.ERROR if failing else EvidenceSeverity.INFO,
        )

    def dump(self) -> list[dict[str, Any]]:
        return [item.model_dump(mode="json") for item in self._items]

    def overhead_ms(self) -> float:
        return round(self._overhead_seconds * 1000, 3)
