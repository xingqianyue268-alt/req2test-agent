"""Real loopback HTTP + generated pytest against a deterministic mock API."""

import base64
import json
import os
import socket
import subprocess
import sys
import time
from pathlib import Path

import httpx
import pytest

from req2test.config import LLMSettings
from req2test.execution_models import ExecutionConfig, HttpTestSpec
from req2test.http_tool import HttpApiTestTool
from req2test.models import ReviewReport, WorkflowResult
from req2test.openapi_import import ContractPlan, compile_plan, parse_document
from req2test.pytest_runner import PytestRunnerTool
from req2test.tool_calling import execute_with_tools

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def mock_url():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    process = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "examples.mock_api:app",
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
            "--no-access-log",
        ],
        cwd=ROOT,
        env=os.environ.copy(),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
    )
    url = f"http://127.0.0.1:{port}"
    try:
        for _ in range(100):
            if process.poll() is not None:
                pytest.fail("Mock API startup failed: " + process.stderr.read().decode())
            try:
                if httpx.get(url + "/openapi.json", timeout=0.2).status_code == 200:
                    break
            except httpx.RequestError:
                pass
            time.sleep(0.05)
        else:
            pytest.fail("Mock API startup timeout")
        yield url
    finally:
        process.terminate()
        process.communicate(timeout=10)


def make_plan(url, extension="json"):
    path = ROOT / "examples" / "openapi" / f"synthetic-shop.{extension}"
    catalog = parse_document(path.name, path.read_bytes())
    assert all(op["supported"] for op in catalog["operations"]), catalog
    return ContractPlan(
        filename=path.name,
        content_base64=base64.b64encode(path.read_bytes()).decode(),
        base_url=url,
        selected_operations=[op["key"] for op in catalog["operations"]],
        headers={"Authorization": "Bearer synthetic-demo-token"},
        overrides={
            "GET /users/{user_id}": {
                "path": {"user_id": 1},
                "expected_json_contains": {"id": 1, "name": "demo"},
            },
            "POST /products": {"expected_json_contains": {"metadata": {"active": True}}},
        },
    )


@pytest.mark.parametrize("extension", ["json", "yaml"])
def test_import_to_both_executors_and_diagnosis(mock_url, extension):
    config = compile_plan(make_plan(mock_url, extension))
    report = execute_with_tools(
        "contract",
        WorkflowResult(
            requirements=[], test_cases=[], review=ReviewReport(score=100, coverage_rate=1)
        ),
        LLMSettings(),
        config,
    )
    assert report.http_results and all(r.passed for r in report.http_results), report.model_dump()
    assert report.pytest_result.passed, report.pytest_result.stdout
    assert report.pytest_result.passed_count == len(config.api_specs)
    assert any(r.status_code == 422 for r in report.http_results)
    assert not report.failure_analysis
    assert report.failure_analysis_v2["summary"]["failure_count"] == 0
    assert "synthetic-demo-token" not in json.dumps(report.model_dump())


@pytest.mark.parametrize("run_http,run_pytest", [(True, False), (False, True), (True, True)])
def test_unexpected_422_is_failure(mock_url, run_http, run_pytest):
    config = ExecutionConfig(
        enabled=True,
        base_url=mock_url,
        run_http_tool=run_http,
        run_pytest=run_pytest,
        api_specs=[
            HttpTestSpec(
                case_id="invalid",
                name="invalid",
                method="POST",
                path="/products",
                json_body={},
                expected_status=200,
            )
        ],
    )
    report = execute_with_tools(
        "contract",
        WorkflowResult(
            requirements=[], test_cases=[], review=ReviewReport(score=100, coverage_rate=1)
        ),
        LLMSettings(),
        config,
    )
    if run_http:
        assert not report.http_results[0].passed
        assert report.failure_analysis[0].category == "contract_mismatch"
    if run_pytest:
        assert not report.pytest_result.passed
        assert report.pytest_result.failed_count == 1


def test_schema_assertion_failure_both_tools(mock_url):
    spec = HttpTestSpec(
        case_id="schema", name="schema", path="/products", expected_json_schema={"type": "object"}
    )
    assert not HttpApiTestTool(mock_url).invoke(spec).passed
    assert PytestRunnerTool().invoke([spec], mock_url).failed_count == 1


def test_schema_never_fetches_external_refs(mock_url):
    spec = HttpTestSpec(
        case_id="schema",
        name="schema",
        path="/products",
        expected_json_schema={"$ref": "http://untrusted.invalid/schema"},
    )
    result = HttpApiTestTool(mock_url).invoke(spec)
    assert not result.passed
    assert "禁止的引用" in result.failures[-1]
    assert not PytestRunnerTool().invoke([spec], mock_url).passed
