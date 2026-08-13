"""Worker milestone and atomic terminal-result persistence."""

from __future__ import annotations

import json
import os
import re
import uuid
from copy import deepcopy
from typing import Any
from urllib.parse import urlparse

from sqlalchemy.orm import Session

from ..models import TaskORM
from ..repositories import executions as execution_repository
from ..repositories import tasks as task_repository
from ..repositories import test_cases as test_case_repository
from .task_persistence import safe_error_summary, sanitize_config


class CeleryDeliveryConflict(RuntimeError):
    """A second Celery delivery attempted to own an existing business Task."""


def _limit_for_key(key: str, default: int) -> int:
    normalized = key.lower()
    if normalized in {"response_excerpt", "stdout", "stderr"}:
        return int(os.getenv("RESULT_TEXT_MAX_CHARS", "4000"))
    if "context" in normalized or "raw" in normalized or "error" in normalized:
        return int(os.getenv("RESULT_TEXT_MAX_CHARS", "4000"))
    return default


def _redact_string(value: str) -> str:
    value = re.sub(r"(?i)bearer\s+[A-Za-z0-9._~+/=-]+", "Bearer ***", value)
    value = re.sub(r"://[^/@\s]+:[^/@\s]+@", "://***:***@", value)
    return re.sub(
        r"(?i)(api[_-]?key|authorization|cookie|credential|password|"
        r"private[_-]?(?:credential|key)|secret|token)\s*[=:]\s*[^\s,;]+",
        r"\1=***",
        value,
    )


def sanitize_result(value: Any, *, key: str = "", default_text_limit: int = 12000) -> Any:
    """Remove nested secrets and bound large text fields in a final result."""

    if isinstance(value, dict):
        sanitized = sanitize_config(value)
        return {
            item_key: sanitize_result(
                item_value, key=item_key, default_text_limit=default_text_limit
            )
            for item_key, item_value in sanitized.items()
        }
    if isinstance(value, (list, tuple)):
        return [
            sanitize_result(item, key=key, default_text_limit=default_text_limit)
            for item in value
        ]
    if isinstance(value, str):
        redacted = _redact_string(value)
        limit = _limit_for_key(key, default_text_limit)
        if len(redacted) > limit:
            return redacted[:limit] + "…[truncated]"
        return redacted
    return value


def _json_size(value: Any) -> int:
    serialized = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    return len(serialized.encode("utf-8"))


def _aggressive_shrink(value: Any, *, key: str = "") -> Any:
    if isinstance(value, dict):
        return {
            item_key: _aggressive_shrink(item, key=item_key)
            for item_key, item in value.items()
        }
    if isinstance(value, list):
        return [_aggressive_shrink(item, key=key) for item in value[:50]]
    if isinstance(value, str):
        limit = 256 if key not in {"title", "case_id", "category", "probable_cause"} else 500
        return value if len(value) <= limit else value[:limit] + "…[truncated]"
    return value


def bound_result_payload(payload: dict[str, Any], max_bytes: int | None = None) -> dict[str, Any]:
    """Keep the structured result recoverable while enforcing a JSONB size budget."""

    limit = max_bytes or int(os.getenv("RESULT_PAYLOAD_MAX_BYTES", "1048576"))
    sanitized = sanitize_result(deepcopy(payload))
    if _json_size(sanitized) <= limit:
        return sanitized

    shrunk = _aggressive_shrink(sanitized)
    shrunk["truncated"] = True
    if _json_size(shrunk) <= limit:
        return shrunk

    execution = shrunk.get("execution") or {}
    compact = {
        "requirements": shrunk.get("requirements", []),
        "test_cases": shrunk.get("test_cases", []),
        "review": shrunk.get("review", {}),
        "retrieved_context": [],
        "execution": {
            "enabled": execution.get("enabled"),
            "summary": execution.get("summary", {}),
            "failure_analysis": execution.get("failure_analysis", []),
            "failure_analysis_v2": execution.get("failure_analysis_v2", {}),
            "diagnostic_evidence": execution.get("diagnostic_evidence", [])[:50],
            "evidence_collection_overhead_ms": execution.get(
                "evidence_collection_overhead_ms", 0.0
            ),
            "pytest_result": execution.get("pytest_result"),
            "warnings": execution.get("warnings", []),
        },
        "errors": shrunk.get("errors", []),
        "truncated": True,
    }
    compact = _aggressive_shrink(compact)
    if _json_size(compact) <= limit:
        return compact

    minimal = {
        "review": compact["review"],
        "execution": {
            "summary": compact["execution"]["summary"],
            "failure_analysis": compact["execution"]["failure_analysis"],
            "failure_analysis_v2": compact["execution"]["failure_analysis_v2"],
        },
        "errors": compact["errors"][:10],
        "truncated": True,
    }
    if _json_size(minimal) <= limit:
        return minimal
    return {
        "execution": {"summary": compact["execution"]["summary"]},
        "errors": ["Result payload exceeded persistence size limit"],
        "truncated": True,
    }


def build_result_summary(payload: dict[str, Any], final_status: str) -> dict[str, Any]:
    requirements = payload.get("requirements") or []
    test_cases = payload.get("test_cases") or []
    review = payload.get("review") or {}
    execution = payload.get("execution") or {}
    execution_summary = execution.get("summary") or {}
    diagnosis_summary = (execution.get("failure_analysis_v2") or {}).get("summary") or {}
    return {
        "total_requirements": len(requirements),
        "total_test_cases": len(test_cases),
        "review_score": review.get("score"),
        "coverage_rate": review.get("coverage_rate"),
        "total_http_cases": execution_summary.get("total_http_cases", 0),
        "passed_http_cases": execution_summary.get("passed_http_cases", 0),
        "failed_http_cases": execution_summary.get("failed_http_cases", 0),
        "http_pass_rate": execution_summary.get("http_pass_rate"),
        "pytest_passed": execution_summary.get("pytest_passed"),
        "failure_analysis_count": int(
            diagnosis_summary.get("failure_count")
            if diagnosis_summary.get("failure_count") is not None
            else len(execution.get("failure_analysis") or [])
        ),
        "primary_failure_category": diagnosis_summary.get("primary_failure_category"),
        "failure_category_counts": diagnosis_summary.get("category_distribution") or {},
        "final_status": final_status,
    }


class ResultPersistenceService:
    def bind_delivery(
        self, session: Session, task_id: str, celery_task_id: str
    ) -> tuple[TaskORM, bool]:
        try:
            parsed_id = uuid.UUID(task_id)
            return task_repository.bind_worker_delivery(session, parsed_id, celery_task_id)
        except ValueError as exc:
            raise CeleryDeliveryConflict(str(exc)) from exc

    def persist_milestone(
        self, session: Session, task_id: str, *, status: str, stage: str, progress: int
    ) -> TaskORM:
        return task_repository.update_task_state(
            session,
            uuid.UUID(task_id),
            status=status,
            stage=stage,
            progress=progress,
            error=None,
        )

    def finalize_completed(
        self, session: Session, task_id: str, payload: dict[str, Any]
    ) -> TaskORM:
        parsed_id = uuid.UUID(task_id)
        bounded_payload = bound_result_payload(payload)

        persisted_cases: dict[str, uuid.UUID] = {}
        for case in bounded_payload.get("test_cases") or []:
            record = test_case_repository.upsert_test_case(
                session,
                task_id=parsed_id,
                case_id=case["case_id"],
                version=int(case.get("version", 1)),
                module=case.get("module") or "通用模块",
                title=case.get("title") or case["case_id"],
                priority=case.get("priority") or "P1",
                test_type=case.get("test_type") or "正向",
                source_requirement=case.get("source_requirement") or "",
                preconditions=case.get("preconditions") or [],
                steps=case.get("steps") or [],
            )
            persisted_cases[record.case_id] = record.id

        execution = bounded_payload.get("execution") or {}
        diagnoses = (execution.get("failure_analysis_v2") or {}).get("diagnoses") or []
        failure_categories = {
            item.get("case_id"): item.get("category") for item in diagnoses
        }
        failure_categories.update(
            {
                item.get("case_id"): item.get("category")
                for item in execution.get("failure_analysis") or []
                if item.get("case_id") not in failure_categories
            }
        )
        specs = {
            item.get("case_id"): item for item in execution.get("executable_cases") or []
        }
        for result in execution.get("http_results") or []:
            case_id = result.get("case_id") or "unknown"
            spec = specs.get(case_id) or {}
            path = urlparse(result.get("url") or "").path or spec.get("path")
            execution_repository.upsert_execution(
                session,
                task_id=parsed_id,
                test_case_id=persisted_cases.get(case_id),
                idempotency_key=f"{parsed_id}:http:{case_id}:1",
                kind="http",
                attempt=1,
                method=result.get("method") or spec.get("method"),
                path=path,
                expected_status=result.get("expected_status"),
                actual_status=result.get("status_code"),
                passed=bool(result.get("passed")),
                duration_ms=result.get("duration_ms"),
                response_excerpt=result.get("response_excerpt"),
                error=result.get("error"),
                failure_category=failure_categories.get(case_id),
            )

        return task_repository.finalize_task(
            session,
            parsed_id,
            status="completed",
            stage="completed",
            progress=100,
            result_summary=build_result_summary(bounded_payload, "completed"),
            result_payload=bounded_payload,
        )

    def finalize_failed(
        self,
        session: Session,
        task_id: str,
        error: BaseException,
        partial_payload: dict[str, Any] | None = None,
        stage: str = "internal_error",
    ) -> TaskORM:
        payload = bound_result_payload(
            {**(partial_payload or {}), "errors": [safe_error_summary(error)]}
        )
        return task_repository.finalize_task(
            session,
            uuid.UUID(task_id),
            status="failed",
            stage=stage,
            progress=100,
            result_summary=build_result_summary(payload, "failed"),
            result_payload=payload,
            error=safe_error_summary(error),
        )
