"""Tests for the HTTP Tool, Pytest Runner and failure-attribution pipeline."""

from __future__ import annotations

import json
import threading
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from req2test.config import LLMSettings
from req2test.execution_models import ExecutionConfig, HttpExecutionResult, HttpTestSpec
from req2test.http_tool import HttpApiTestTool
from req2test.pytest_runner import PytestRunnerTool, render_pytest_module
from req2test.tool_calling import analyse_failures, extract_explicit_http_specs


class _Handler(BaseHTTPRequestHandler):
    def do_GET(self):  # noqa: N802 - BaseHTTPRequestHandler API
        if self.path == "/health":
            payload = json.dumps({"status": "ok", "service": "fixture"}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
            return
        self.send_response(404)
        self.end_headers()

    def log_message(self, format, *args):  # noqa: A002 - inherited method signature
        return


@contextmanager
def _local_http_server():
    server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def _health_spec(expected_status: int = 200) -> HttpTestSpec:
    return HttpTestSpec(
        case_id="API-001",
        name="健康检查",
        method="GET",
        path="/health",
        expected_status=expected_status,
        expected_json_contains={"status": "ok"},
    )


def test_extract_explicit_http_specs_does_not_invent_endpoint():
    text = """
用户可以新增供应商。
GET /api/health 状态码: 200 响应包含: {"status":"ok"}
未给出接口的普通功能需求。
"""
    specs = extract_explicit_http_specs(text)
    assert len(specs) == 1
    assert specs[0].method == "GET"
    assert specs[0].path == "/api/health"
    assert specs[0].expected_json_contains == {"status": "ok"}


def test_http_api_tool_executes_real_local_request():
    with _local_http_server() as base_url:
        result = HttpApiTestTool(base_url).invoke(_health_spec())
    assert result.passed is True
    assert result.status_code == 200
    assert result.failures == []


def test_http_api_tool_records_assertion_failure():
    with _local_http_server() as base_url:
        result = HttpApiTestTool(base_url).invoke(_health_spec(expected_status=201))
    assert result.passed is False
    assert result.status_code == 200
    assert any("状态码不一致" in item for item in result.failures)


def test_http_api_tool_blocks_unapproved_remote_target(monkeypatch):
    monkeypatch.setenv("REQ2TEST_ALLOW_REMOTE_EXECUTION", "false")
    monkeypatch.setenv("REQ2TEST_EXECUTION_ALLOWED_HOSTS", "localhost,127.0.0.1,api")
    with pytest.raises(ValueError, match="不在执行白名单"):
        HttpApiTestTool("https://example.com")


def test_pytest_runner_executes_generated_http_suite():
    with _local_http_server() as base_url:
        result = PytestRunnerTool(timeout_seconds=15).invoke([_health_spec()], base_url)
    assert result.passed is True
    assert result.exit_code == 0
    assert result.passed_count == 1


def test_rendered_pytest_is_template_based_not_arbitrary_source():
    source = render_pytest_module([_health_spec()], "http://127.0.0.1:8000")
    assert "test_generated_http_case" in source
    assert "API-001" in source
    assert "httpx.Client" in source


def test_failure_analysis_classifies_authentication():
    failed = HttpExecutionResult(
        case_id="API-401",
        name="受保护接口",
        method="GET",
        url="http://example.test/private",
        passed=False,
        status_code=401,
        expected_status=200,
        failures=["状态码不一致：期望 200，实际 401"],
    )
    analyses, warnings = analyse_failures(
        [failed],
        LLMSettings(mode="demo"),
        ExecutionConfig(enabled=True, base_url="http://example.test"),
    )
    assert warnings == []
    assert analyses[0].category == "authentication"
