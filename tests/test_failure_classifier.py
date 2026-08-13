from __future__ import annotations

from req2test.diagnostics.classifier import classify_failures
from req2test.diagnostics.evidence import (
    EvidenceCollector,
    EvidenceSeverity,
    EvidenceType,
    TraceContext,
)
from req2test.execution_models import HttpExecutionResult, HttpTestSpec


def _collector() -> EvidenceCollector:
    return EvidenceCollector(TraceContext.for_task("trace-1", "delivery-1"))


def _http(status: int, *, expected: int = 200, validation: str | None = None):
    collector = _collector()
    spec = HttpTestSpec(case_id=f"API-{status}", name="fixture", path="/fixture", expected_status=expected)
    collector.collect_http(
        spec,
        HttpExecutionResult(
            case_id=spec.case_id,
            name=spec.name,
            method="GET",
            url="http://api/fixture",
            passed=status == expected,
            status_code=status,
            expected_status=expected,
            failures=[] if status == expected else [f"expected {expected}, got {status}"],
            validation_error=validation,
            response_excerpt=validation or f"upstream returned {status}",
        ),
    )
    return collector


def _category(collector: EvidenceCollector) -> str:
    result = classify_failures(collector.items, trace_id="trace-1")
    assert result.diagnoses
    diagnosis = result.diagnoses[0]
    assert diagnosis.evidence_refs
    assert diagnosis.evidence_summary
    return diagnosis.category


def test_422_with_validation_evidence_is_contract_mismatch():
    assert _category(_http(422, validation='{"type":"missing","loc":["body","name"]}')) == "contract_mismatch"


def test_422_without_validation_evidence_is_not_strong_contract_conclusion():
    assert _category(_http(422)) == "assertion_failure"


def test_401_is_authentication_error():
    assert _category(_http(401)) == "authentication_error"


def test_target_500_is_upstream_api_error():
    assert _category(_http(500)) == "upstream_api_error"


def test_timeout_has_high_confidence_and_supported_suggestion():
    collector = _collector()
    spec = HttpTestSpec(case_id="API-T", name="slow", path="/slow")
    collector.collect_http(
        spec,
        HttpExecutionResult(
            case_id="API-T",
            name="slow",
            method="GET",
            url="http://api/slow",
            passed=False,
            expected_status=200,
            timed_out=True,
            failures=["timeout"],
            error="ReadTimeout",
        ),
    )
    result = classify_failures(collector.items, trace_id="trace-1")
    diagnosis = result.diagnoses[0]
    assert diagnosis.category == "timeout"
    assert diagnosis.confidence == "high"
    assert "timeout" in diagnosis.suggestion


def test_pytest_assertion_failure():
    collector = _collector()
    collector.add(
        EvidenceType.PYTEST,
        stage="pytest",
        summary="Pytest suite failed",
        details={"exit_code": 1, "assertion_summary": ["assert 1 == 2"]},
        severity=EvidenceSeverity.ERROR,
    )
    assert _category(collector) == "assertion_failure"


def test_empty_rag_retrieval_is_medium_confidence_issue():
    collector = _collector()
    collector.collect_rag(query="rules", top_k=4, contexts=[])
    result = classify_failures(collector.items, trace_id="trace-1")
    assert result.diagnoses[0].category == "rag_retrieval_issue"
    assert result.diagnoses[0].confidence == "medium"


def test_llm_structured_output_failure():
    collector = _collector()
    collector.collect_generation(
        provider="demo",
        model="fixture",
        duration_ms=5,
        parse_success=False,
        generated_case_count=0,
        validation_issues=["invalid structured output"],
        review_score=None,
    )
    assert _category(collector) == "llm_output_issue"


def test_redis_or_database_worker_exception_is_environment_error():
    collector = _collector()
    collector.collect_worker(
        event="exception",
        stage="persistence",
        exception=RuntimeError("Redis unavailable"),
    )
    assert _category(collector) == "environment_error"


def test_platform_worker_exception_is_internal_error_not_upstream():
    collector = _collector()
    collector.collect_worker(
        event="exception",
        stage="generation",
        exception=ValueError("unexpected internal state"),
    )
    assert _category(collector) == "internal_error"


def test_unknown_fallback_is_low_confidence_when_error_has_no_matching_rule():
    collector = _collector()
    collector.add(
        EvidenceType.SYSTEM,
        stage="unknown",
        summary="Unclassified failure signal",
        severity=EvidenceSeverity.ERROR,
    )
    result = classify_failures(collector.items, trace_id="trace-1")
    assert result.diagnoses[0].category == "unknown"
    assert result.diagnoses[0].confidence == "low"


def test_multi_failure_summary_uses_severity_priority_then_distribution():
    timeout = _collector()
    timeout.add(
        EvidenceType.TIMEOUT,
        stage="http_execution",
        summary="timeout",
        severity=EvidenceSeverity.ERROR,
        context=timeout.context.child(case_id="API-1"),
    )
    auth = _collector()
    auth.collect_http(
        HttpTestSpec(case_id="API-2", name="auth", path="/auth"),
        HttpExecutionResult(
            case_id="API-2",
            name="auth",
            method="GET",
            url="http://api/auth",
            passed=False,
            status_code=401,
            expected_status=200,
            failures=["unauthorized"],
        ),
    )
    result = classify_failures(timeout.items + auth.items, trace_id="trace-1")
    assert result.summary.failure_count == 2
    assert result.summary.category_distribution == {
        "authentication_error": 1,
        "timeout": 1,
    }
    assert result.summary.primary_failure_category == "timeout"


def test_success_evidence_does_not_create_fake_diagnosis():
    collector = _http(200)
    result = classify_failures(collector.items, trace_id="trace-1")
    assert result.diagnoses == []
    assert result.summary.failure_count == 0
    assert result.summary.primary_failure_category is None
