"""Integration-style test for generation -> tool dispatch -> Pytest -> summary."""

from __future__ import annotations

import json
import threading
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from req2test.config import GenerationConfig, LLMSettings
from req2test.execution_models import ExecutionConfig, HttpTestSpec
from req2test.graph import run_workflow
from req2test.tool_calling import execute_with_tools


class _TargetHandler(BaseHTTPRequestHandler):
    def do_GET(self):  # noqa: N802
        if self.path == "/api/status":
            body = json.dumps({"status": "ok", "version": "test"}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        self.send_response(404)
        self.end_headers()

    def log_message(self, format, *args):  # noqa: A002
        return


@contextmanager
def _target_server():
    server = ThreadingHTTPServer(("127.0.0.1", 0), _TargetHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_generation_can_continue_into_real_tool_execution():
    requirement = """
# 状态查询
系统提供状态查询能力。
GET /api/status 状态码: 200 响应包含: {"status":"ok"}
"""
    settings = LLMSettings(mode="demo")
    generated = run_workflow(
        requirement,
        llm_settings=settings,
        generation_config=GenerationConfig(max_cases=4),
    )
    assert generated.test_cases

    with _target_server() as base_url:
        report = execute_with_tools(
            requirement_text=requirement,
            workflow_result=generated,
            llm_settings=settings,
            config=ExecutionConfig(
                enabled=True,
                base_url=base_url,
                api_specs=[
                    HttpTestSpec(
                        case_id="API-STATUS",
                        name="状态查询接口",
                        method="GET",
                        path="/api/status",
                        expected_status=200,
                        expected_json_contains={"status": "ok"},
                    )
                ],
            ),
        )

    assert report.summary["status"] == "completed"
    assert report.summary["passed_http_cases"] == 1
    assert report.summary["pytest_passed"] is True
    assert [call.tool_name for call in report.tool_calls] == ["http_api_test", "pytest_runner"]
    assert report.failure_analysis == []
