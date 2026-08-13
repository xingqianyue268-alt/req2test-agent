from __future__ import annotations

from req2test.diagnostics.evidence import (
    EvidenceCollector,
    EvidenceType,
    TraceContext,
    sanitize_evidence,
)
from req2test.execution_models import (
    HttpExecutionResult,
    HttpTestSpec,
    PytestExecutionResult,
)


def _context() -> TraceContext:
    return TraceContext.for_task("task-123", "celery-456")


def test_trace_id_is_created_from_business_task_and_preserved_by_child_context():
    context = _context()
    child = context.child(case_id="API-001", execution_id="exec-1")
    assert context.trace_id == context.task_id == "task-123"
    assert child.trace_id == context.trace_id
    assert child.celery_task_id == "celery-456"
    assert child.case_id == "API-001"


def test_http_request_and_response_evidence_only_keeps_allowlisted_headers():
    collector = EvidenceCollector(_context())
    spec = HttpTestSpec(
        case_id="API-001",
        name="create",
        method="POST",
        path="/items",
        headers={"Content-Type": "application/json", "Authorization": "Bearer secret"},
        query={"page": 1},
        json_body={"name": "safe", "password": "hidden"},
        expected_status=201,
    )
    result = HttpExecutionResult(
        case_id="API-001",
        name="create",
        method="POST",
        url="http://api/items",
        passed=True,
        status_code=201,
        expected_status=201,
        duration_ms=12.5,
        response_content_type="application/json",
        response_excerpt='{"id": 1}',
    )
    collector.collect_http(spec, result)
    request, response = collector.dump()
    assert request["evidence_type"] == "http_request"
    assert request["details"]["headers"] == {"Content-Type": "application/json"}
    assert request["details"]["body_summary"]["password"] == "***"
    assert response["evidence_type"] == "http_response"
    assert response["details"]["content_type"] == "application/json"


def test_422_contract_validation_evidence_is_structured_and_factual():
    collector = EvidenceCollector(_context())
    spec = HttpTestSpec(
        case_id="API-422", name="echo", method="POST", path="/echo", expected_status=200
    )
    result = HttpExecutionResult(
        case_id="API-422",
        name="echo",
        method="POST",
        url="http://api/echo",
        passed=False,
        status_code=422,
        expected_status=200,
        failures=["状态码不一致"],
        validation_error='{"detail":[{"loc":["body","message"],"type":"missing"}]}',
    )
    collector.collect_http(spec, result)
    validation = next(
        item for item in collector.dump() if item["evidence_type"] == "validation"
    )
    assert validation["details"]["expected_status"] == 200
    assert validation["details"]["actual_status"] == 422
    assert validation["details"]["suspected_contract_issue"] is True
    assert "message" in validation["details"]["validation_error"]


def test_timeout_evidence_records_duration_without_inventing_status():
    collector = EvidenceCollector(_context())
    spec = HttpTestSpec(case_id="API-T", name="slow", path="/slow")
    result = HttpExecutionResult(
        case_id="API-T",
        name="slow",
        method="GET",
        url="http://api/slow",
        passed=False,
        expected_status=200,
        duration_ms=501.2,
        timed_out=True,
        failures=["请求超时"],
        error="ReadTimeout",
    )
    collector.collect_http(spec, result)
    timeout = next(item for item in collector.dump() if item["evidence_type"] == "timeout")
    assert timeout["details"]["duration_ms"] == 501.2
    response = next(
        item for item in collector.dump() if item["evidence_type"] == "http_response"
    )
    assert response["details"]["actual_status"] is None


def test_pytest_assertion_evidence_extracts_node_and_bounds_output():
    collector = EvidenceCollector(_context())
    collector.collect_pytest(
        PytestExecutionResult(
            passed=False,
            exit_code=1,
            duration_ms=42,
            failed_count=1,
            stdout=("FAILED test_generated.py::test_case - AssertionError\n" + "x" * 9000),
            stderr="E       assert 422 == 200",
        )
    )
    item = collector.dump()[0]
    assert item["details"]["failed_node_ids"] == ["test_generated.py::test_case"]
    assert any(
        "assert 422 == 200" in line
        for line in item["details"]["assertion_summary"]
    )
    assert len(item["details"]["stdout_excerpt"]) < 1600


def test_rag_evidence_records_query_top_k_results_and_empty_retrieval():
    collector = EvidenceCollector(_context())
    collector.collect_rag(query="boundary tests", top_k=4, contexts=[])
    item = collector.items[0]
    assert item.evidence_type == EvidenceType.RAG_RETRIEVAL
    assert item.details["returned_count"] == 0
    assert item.details["top_k"] == 4
    assert item.severity == "warning"


def test_generation_evidence_records_structured_parse_failure_without_prompt():
    collector = EvidenceCollector(_context())
    collector.collect_generation(
        provider="openai_compatible",
        model="test-model",
        duration_ms=91,
        parse_success=False,
        generated_case_count=0,
        validation_issues=["invalid JSON"],
        review_score=None,
    )
    item = collector.dump()[0]
    assert item["evidence_type"] == "llm_generation"
    assert item["details"]["structured_output_parse_success"] is False
    assert "prompt" not in str(item).lower()


def test_worker_exception_evidence_has_type_stage_and_retry_count():
    collector = EvidenceCollector(_context())
    collector.collect_worker(
        event="exception",
        stage="execution_failed",
        retry_count=2,
        exception=RuntimeError("api_key=do-not-store"),
    )
    item = collector.dump()[0]
    assert item["evidence_type"] == "worker_exception"
    assert item["details"]["exception_type"] == "RuntimeError"
    assert "do-not-store" not in str(item)


def test_infrastructure_evidence_only_represents_supplied_check_results():
    collector = EvidenceCollector(_context())
    collector.collect_infrastructure(
        {
            "PostgreSQL": {"state": "healthy", "basis": "SELECT 1"},
            "RabbitMQ": {"state": "unknown", "basis": "not probed"},
        }
    )
    checks = collector.dump()[0]["details"]["checks"]
    assert checks["PostgreSQL"]["state"] == "healthy"
    assert checks["RabbitMQ"]["state"] == "unknown"
    assert "Redis" not in checks


def test_nested_secret_sanitization_is_case_insensitive_and_recursive():
    value = {
        "Headers": {
            "Authorization": "Bearer abc",
            "Set-Cookie": "session=abc",
            "X-API-Key": "key",
            "safe": [{"Client-Secret": "secret"}],
        },
        "message": "password=hunter2 token=abc",
    }
    cleaned = sanitize_evidence(value)
    rendered = str(cleaned)
    for secret in ("hunter2", "Bearer abc", "session=abc", "Client-Secret': 'secret"):
        assert secret not in rendered
    assert cleaned["Headers"]["Authorization"] == "***"
    assert cleaned["Headers"]["Set-Cookie"] == "***"


def test_large_nested_evidence_is_truncated_before_persistence():
    cleaned = sanitize_evidence(
        {"response_excerpt": "x" * 10000, "events": list(range(100))}
    )
    assert cleaned["response_excerpt"].endswith("…[truncated]")
    assert len(cleaned["events"]) == 51
    assert "items truncated" in cleaned["events"][-1]


def test_evidence_overhead_measures_collection_work_not_elapsed_wall_time():
    import time

    collector = EvidenceCollector(_context())
    time.sleep(0.02)
    collector.add(
        EvidenceType.SYSTEM,
        stage="measurement",
        summary="one bounded event",
    )
    assert collector.overhead_ms() < 10
