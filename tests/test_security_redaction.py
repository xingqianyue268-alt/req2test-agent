"""P0 regressions for redaction across existing public output boundaries."""

import json
import logging
from types import SimpleNamespace
from unittest.mock import Mock

import httpx
import pytest

from req2test.config import LLMSettings
from req2test.db.services.result_persistence import bound_result_payload, sanitize_result
from req2test.diagnostics.evidence import EvidenceCollector, TraceContext, sanitize_evidence
from req2test.evaluation.safety import safe_failure_reason
from req2test.execution_models import ExecutionConfig, HttpExecutionResult, HttpTestSpec
from req2test.exporters import to_csv_bytes, to_json_text, to_markdown
from req2test.http_tool import HttpApiTestTool
from req2test.llm import invoke_json
from req2test.models import ReviewReport, WorkflowResult
from req2test.pytest_runner import PytestRunnerTool
from req2test.services.knowledge_service import _safe_error
from req2test.task_store import TaskStore
from req2test.tool_calling import analyse_failures

TEXT_CASES = [
    ('{"token":"SYNTHETIC_TOKEN"}', "SYNTHETIC_TOKEN"),
    ("{'access_token': 'SYNTHETIC_ACCESS'}", "SYNTHETIC_ACCESS"),
    ('{"Authorization":"Basic SYNTHETIC_BASIC"}', "SYNTHETIC_BASIC"),
    ("Cookie: sid=SYNTHETIC_COOKIE; other=SYNTHETIC_OTHER", "SYNTHETIC_OTHER"),
    ('{"nested":{"apiKey":"SYNTHETIC_KEY"}}', "SYNTHETIC_KEY"),
    (
        "https://user:SYNTHETIC_PASSWORD@localhost/path?token=SYNTHETIC_QUERY&status=ok",
        "SYNTHETIC_QUERY",
    ),
    (
        '{"email":"synthetic-person@example.test","phone":"13800000000"}',
        "synthetic-person@example.test",
    ),
    ('{"password":"SYNTHETIC_ESCAPED\\"SECRET"}', "SYNTHETIC_ESCAPED"),
    (
        '{"detail":[{"loc":["body","password"],"input":"SYNTHETIC_VALIDATION"}]}',
        "SYNTHETIC_VALIDATION",
    ),
]


@pytest.mark.parametrize("text,secret", TEXT_CASES)
@pytest.mark.parametrize(
    "sanitize", [sanitize_result, sanitize_evidence, safe_failure_reason, _safe_error]
)
def test_all_existing_sanitizers_share_secret_handling(text, secret, sanitize):
    cleaned = sanitize(text)
    assert secret not in str(cleaned)


def test_http_assertions_use_original_values_but_reports_are_redacted(monkeypatch):
    client_type = httpx.Client

    def respond(request):
        assert request.headers["Authorization"] == "Bearer SYNTHETIC_REQUEST"
        return httpx.Response(200, json={"token": "SYNTHETIC_RESPONSE", "status": "ok"})

    monkeypatch.setattr(
        httpx,
        "Client",
        lambda **kwargs: client_type(transport=httpx.MockTransport(respond), **kwargs),
    )
    spec = HttpTestSpec(
        case_id="ONE",
        name="one",
        path="/ok",
        headers={"Authorization": "Bearer SYNTHETIC_REQUEST"},
        expected_json_contains={"token": "SYNTHETIC_RESPONSE", "status": "ok"},
    )
    result = HttpApiTestTool("http://localhost").invoke(spec)
    assert result.passed
    assert "SYNTHETIC_RESPONSE" not in result.model_dump_json()
    assert "ok" in result.response_excerpt
    assert spec.headers["Authorization"] == "Bearer SYNTHETIC_REQUEST"


def test_http_errors_and_pytest_output_redact_before_truncation(monkeypatch):
    output = "x" * 8100 + '\n{"token":"SYNTHETIC_OUTPUT"}\n1 failed'
    monkeypatch.setattr(
        "req2test.pytest_runner.subprocess.run",
        lambda *a, **k: SimpleNamespace(
            returncode=1, stdout=output, stderr="password=SYNTHETIC_STDERR"
        ),
    )
    result = PytestRunnerTool().invoke(
        [HttpTestSpec(case_id="ONE", name="one", path="/")], "http://localhost"
    )
    assert result.failed_count == 1
    assert "SYNTHETIC_OUTPUT" not in result.stdout
    assert "SYNTHETIC_STDERR" not in result.stderr


def test_timeout_output_is_also_redacted(monkeypatch):
    import subprocess

    def timeout(*_args, **_kwargs):
        raise subprocess.TimeoutExpired("pytest", 1, output=b'{"token":"SYNTHETIC_TIMEOUT"}')

    monkeypatch.setattr("req2test.pytest_runner.subprocess.run", timeout)
    result = PytestRunnerTool().invoke(
        [HttpTestSpec(case_id="ONE", name="one", path="/")], "http://localhost"
    )
    assert result.exit_code == 124
    assert "SYNTHETIC_TIMEOUT" not in result.stdout


def test_persistence_evidence_and_live_projection_do_not_retain_secret(monkeypatch):
    raw = '{"token":"SYNTHETIC_OUTPUT","status":"ok"}'
    result = HttpExecutionResult(
        case_id="ONE",
        name="one",
        method="GET",
        url="http://localhost",
        passed=False,
        expected_status=200,
        response_excerpt=raw,
        error=raw,
    )
    collector = EvidenceCollector(TraceContext.for_task("local"))
    collector.collect_http(HttpTestSpec(case_id="ONE", name="one", path="/"), result)
    payload = {
        "execution": {
            "http_results": [result.model_dump()],
            "diagnostic_evidence": collector.dump(),
        },
        "error": raw,
    }
    assert "SYNTHETIC_OUTPUT" not in json.dumps(bound_result_payload(payload))
    store = TaskStore(redis_url="redis://127.0.0.1:1/0", allow_memory_fallback=True)
    state = store.update("local", **payload)
    assert "SYNTHETIC_OUTPUT" not in json.dumps(state)
    assert "SYNTHETIC_OUTPUT" not in json.dumps(store.get("local"))
    # Simulate a pre-hardening Redis record; read boundaries must also redact it.
    redis = Mock()
    redis.get.return_value = json.dumps(payload)
    store._redis = redis
    assert "SYNTHETIC_OUTPUT" not in json.dumps(store.get("legacy"))


def test_llm_outbound_messages_redact_requirement_and_evidence():
    model = Mock()
    model.invoke.return_value = SimpleNamespace(content='{"status":"ok"}')
    assert invoke_json(model, "token=SYNTHETIC_SYSTEM", '{"password":"SYNTHETIC_PROMPT"}') == {
        "status": "ok"
    }
    messages = model.invoke.call_args.args[0]
    assert "SYNTHETIC_SYSTEM" not in messages[0].content
    assert "SYNTHETIC_PROMPT" not in messages[1].content


def test_failure_analysis_payload_is_safe_even_for_alternate_adapter(monkeypatch):
    captured = []
    monkeypatch.setattr("req2test.tool_calling.build_chat_model", lambda *_: object())
    monkeypatch.setattr(
        "req2test.tool_calling.invoke_json",
        lambda _model, _system, user: captured.append(user) or [],
    )
    result = HttpExecutionResult(
        case_id="ONE",
        name="one",
        method="GET",
        url="http://localhost/?token=SYNTHETIC_URL",
        passed=False,
        expected_status=200,
        failures=['{"token":"SYNTHETIC_FAILURE"}'],
    )
    analyse_failures([result], LLMSettings(mode="openai_compatible"), ExecutionConfig())
    assert (
        captured and "SYNTHETIC_FAILURE" not in captured[0] and "SYNTHETIC_URL" not in captured[0]
    )


@pytest.mark.parametrize("exporter", [to_markdown, to_csv_bytes, to_json_text])
def test_exports_redact_fields_without_mutating_workflow(exporter):
    result = WorkflowResult(
        requirements=[],
        test_cases=[
            {
                "case_id": "ONE",
                "module": "local",
                "title": "token=SYNTHETIC_TITLE",
                "source_requirement": "REQ-1",
                "steps": [
                    {
                        "order": 1,
                        "action": '{"password":"SYNTHETIC_EXPORT"}',
                        "expected": "status=ok",
                    }
                ],
            }
        ],
        review=ReviewReport(score=100, coverage_rate=1),
    )
    output = exporter(result)
    if isinstance(output, bytes):
        output = output.decode("utf-8-sig")
    assert "SYNTHETIC_TITLE" not in output and "SYNTHETIC_EXPORT" not in output
    assert "SYNTHETIC_TITLE" in result.test_cases[0].title


def test_worker_exception_logs_do_not_retain_secrets(caplog, monkeypatch):
    from req2test.worker import logger

    # Alembic fileConfig disables existing loggers during database fixtures.
    monkeypatch.setattr(logger, "disabled", False)
    with caplog.at_level(logging.ERROR):
        try:
            raise RuntimeError('{"token":"SYNTHETIC_EXCEPTION"}')
        except RuntimeError:
            logger.exception("failure payload=%s", {"Authorization": "Basic SYNTHETIC_LOG"})
    assert "SYNTHETIC_EXCEPTION" not in caplog.text
    assert "SYNTHETIC_LOG" not in caplog.text
    assert "RuntimeError" in caplog.text


def test_celery_failure_and_retry_metadata_do_not_emit_raw_secrets(monkeypatch):
    from req2test import worker

    def failure(*_args, **_kwargs):
        raise ValueError('{"token":"SYNTHETIC_CELERY_ERROR"}')

    monkeypatch.setattr(worker, "_generate_test_cases_once", failure)
    with pytest.raises(ValueError) as captured:
        worker.generate_test_cases.run("local", "local", {}, {}, {})
    assert "SYNTHETIC_CELERY_ERROR" not in str(captured.value)


def test_celery_publish_metadata_hides_credentials_without_changing_arguments(monkeypatch):
    import req2test.evaluation_api as evaluations
    from req2test import api

    for publisher, task in [
        (api._publish_task, api.generate_test_cases),
        (evaluations._publish_evaluation, evaluations.run_evaluation),
    ]:
        send = Mock(return_value=SimpleNamespace(id="sent"))
        monkeypatch.setattr(task, "apply_async", send)
        args = ["task", {"api_key": "SYNTHETIC_QUEUE_KEY"}]
        publisher(args, False)
        options = send.call_args.kwargs
        assert options["args"] == args
        assert "SYNTHETIC_QUEUE_KEY" not in options.get("argsrepr", repr(args))


def test_http_client_logs_redact_query_and_transport_debug(monkeypatch, caplog):
    client_type = httpx.Client

    def respond(_request):
        logging.getLogger("httpcore.http11").debug(
            "receive_response_headers.complete return_value=%r",
            [(b"set-cookie", b"sid=SYNTHETIC_TRANSPORT")],
        )
        return httpx.Response(200, json={"status": "ok"})

    monkeypatch.setattr(
        httpx,
        "Client",
        lambda **kwargs: client_type(transport=httpx.MockTransport(respond), **kwargs),
    )
    for name in ("httpx", "httpcore.http11"):
        monkeypatch.setattr(logging.getLogger(name), "disabled", False)
    with caplog.at_level(logging.DEBUG):
        result = HttpApiTestTool("http://localhost").invoke(
            HttpTestSpec(
                case_id="ONE", name="one", path="/ok", query={"token": "SYNTHETIC_QUERY_LOG"}
            )
        )
    assert result.passed
    assert "HTTP Request" in caplog.text
    assert "SYNTHETIC_QUERY_LOG" not in caplog.text
    assert "SYNTHETIC_TRANSPORT" not in caplog.text


def test_missing_expected_text_does_not_echo_unlabelled_secret(monkeypatch):
    client_type = httpx.Client
    monkeypatch.setattr(
        httpx,
        "Client",
        lambda **kwargs: client_type(
            transport=httpx.MockTransport(lambda _: httpx.Response(200, text="ok")), **kwargs
        ),
    )
    result = HttpApiTestTool("http://localhost").invoke(
        HttpTestSpec(
            case_id="ONE",
            name="one",
            path="/ok",
            expected_text_contains=["SYNTHETIC_EXPECTED_SECRET"],
        )
    )
    assert not result.passed
    assert "SYNTHETIC_EXPECTED_SECRET" not in result.model_dump_json()


def test_celery_legacy_replay_result_is_sanitized(monkeypatch):
    from req2test import worker

    raw = {"result": {"password": "SYNTHETIC_LEGACY_RESULT"}}
    monkeypatch.setattr(worker, "_generate_test_cases_once", lambda *_: raw)
    result = worker.generate_test_cases.run("local", "local", {}, {}, {})
    assert "SYNTHETIC_LEGACY_RESULT" not in json.dumps(result)
    assert raw["result"]["password"] == "SYNTHETIC_LEGACY_RESULT"


def test_celery_validation_error_does_not_echo_sensitive_input():
    from pydantic import ValidationError

    from req2test.security.redaction import safe_task_error

    with pytest.raises(ValidationError) as captured:
        LLMSettings(api_key={"opaque": "SYNTHETIC_INVALID_KEY"})
    error = safe_task_error(captured.value)
    assert "SYNTHETIC_INVALID_KEY" not in str(error)
    assert "api_key" in str(error)


def test_celery_retry_traceback_and_republished_metadata_are_safe(monkeypatch):
    import traceback

    from celery.exceptions import Retry

    from req2test import worker

    def failure(*_args, **_kwargs):
        raise ConnectionError('{"token":"SYNTHETIC_RETRY_SECRET"}')

    options = {}

    def retry(**kwargs):
        options.update(kwargs)
        raise Retry(exc=kwargs["exc"])

    monkeypatch.setattr(worker, "_generate_test_cases_once", failure)
    monkeypatch.setattr(worker, "_record_retry", lambda *a, **k: None)
    monkeypatch.setattr(worker.generate_test_cases, "retry", retry)
    with pytest.raises(Retry) as captured:
        worker.generate_test_cases.run("local", "local", {}, {}, {})
    assert "SYNTHETIC_RETRY_SECRET" not in "".join(traceback.format_exception(captured.value))
    assert options.get("argsrepr") == "<redacted task inputs>"


def test_celery_delivery_conflict_keeps_type_without_raw_exception_context(monkeypatch):
    import traceback

    from req2test import worker

    def failure(*_args, **_kwargs):
        raise worker.CeleryDeliveryConflict('{"token":"SYNTHETIC_CONFLICT"}')

    monkeypatch.setattr(worker, "_generate_test_cases_once", failure)
    with pytest.raises(worker.CeleryDeliveryConflict) as captured:
        worker.generate_test_cases.run("local", "local", {}, {}, {})
    assert "SYNTHETIC_CONFLICT" not in "".join(traceback.format_exception(captured.value))
