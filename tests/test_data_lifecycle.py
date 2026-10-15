"""Real local isolation, single-write dual mode, failures and parent cleanup."""

import base64
import json
import time
import xml.etree.ElementTree as ET

import httpx
import pytest
from test_openapi_execution import mock_url as mock_url  # noqa: PLC0414 - shared pytest fixture

from req2test.config import LLMSettings
from req2test.data_driven import DataDrivenPlan, DatasetUpload, compile_data_plan
from req2test.execution_models import ExecutionConfig, HttpTestSpec
from req2test.junit_report import to_junit_xml
from req2test.mock_lifecycle import validate_mock_target
from req2test.models import ReviewReport, WorkflowResult
from req2test.tool_calling import execute_with_tools

PRODUCT = {"name": "repeatable", "price": 1, "metadata": {"active": True, "tags": ["demo"]}}


def execute(config):
    return execute_with_tools(
        "local",
        WorkflowResult(
            requirements=[], test_cases=[], review=ReviewReport(score=100, coverage_rate=1)
        ),
        LLMSettings(),
        config,
    )


@pytest.fixture(autouse=True)
def opt_in(monkeypatch):
    monkeypatch.setenv("REQ2TEST_ENV", "test")
    monkeypatch.setenv("REQ2TEST_ENABLE_MOCK_LIFECYCLE", "true")


def test_login_dataset_continues_after_failure_and_pytest_agrees(mock_url):
    rows = [
        {
            "id": "valid",
            "json_body": {"username": "demo", "password": "demo"},
            "expected_status": 200,
        },
        {
            "id": "wrong-password",
            "json_body": {"username": "demo", "password": "incorrect"},
            "expected_status": 401,
        },
        {"id": "missing", "json_body": {}, "expected_status": 422},
        {"id": "intentional-mismatch", "json_body": {}, "expected_status": 200},
        {
            "id": "last",
            "json_body": {"username": "demo", "password": "demo"},
            "expected_status": 200,
        },
    ]
    config = compile_data_plan(
        DataDrivenPlan(
            template=HttpTestSpec(case_id="LOGIN", name="login", method="POST", path="/login"),
            dataset=DatasetUpload(
                filename="login.json",
                content_base64=base64.b64encode(json.dumps(rows).encode()).decode(),
            ),
            base_url=mock_url,
        )
    )
    report = execute(config)
    assert [r.passed for r in report.http_results] == [True, True, True, False, True]
    assert [r.passed for r in report.pytest_result.case_results] == [True, True, True, False, True]
    assert report.pytest_result.failed_count == 1 and report.pytest_result.passed_count == 4
    assert report.summary["pytest_replayed_cases"] == 5
    xml = to_junit_xml(report.model_dump())
    root = ET.fromstring(xml)
    assert root.attrib["tests"] == "10" and root.attrib["failures"] == "2"
    assert root.attrib["errors"] == "0" and root.attrib["skipped"] == "0"
    assert "incorrect" not in xml
    assert len(root.findall(".//testcase")) == 10


@pytest.mark.parametrize("http,pytest_runner", [(True, False), (False, True), (True, True)])
def test_repeat_create_update_delete_isolated_and_no_duplicate_writes(
    mock_url, http, pytest_runner
):
    create = HttpTestSpec(
        case_id="create",
        name="create",
        method="POST",
        path="/isolated/products",
        json_body=PRODUCT,
        expected_status=201,
        assertions=[
            {"path": "/writes", "op": "eq", "expected": 1},
            {"path": "/product/metadata/tags", "op": "length", "expected": 1},
        ],
    )
    update = HttpTestSpec(
        case_id="update",
        name="update",
        method="PUT",
        path="/isolated/products/repeatable",
        json_body={**PRODUCT, "price": 2},
        assertions=[
            {"path": "/writes", "op": "eq", "expected": 2},
            {"path": "/product/price", "op": "min", "expected": 2},
        ],
    )
    delete = HttpTestSpec(
        case_id="delete",
        name="delete",
        method="DELETE",
        path="/isolated/products/repeatable",
        expected_status=204,
    )
    config = ExecutionConfig(
        enabled=True,
        base_url=mock_url,
        api_specs=[
            create,
            HttpTestSpec(
                case_id="read-between-writes",
                name="read",
                path="/isolated/products",
                assertions=[
                    {"path": "/items", "op": "length", "expected": 1},
                    {"path": "/writes", "op": "eq", "expected": 1},
                ],
            ),
            update,
            delete,
        ],
        mock_isolation=True,
        run_http_tool=http,
        run_pytest=pytest_runner,
    )
    run_ids = []
    for _ in range(2):
        report = execute(config)
        assert report.lifecycle["cleanup"] == "passed"
        if http:
            assert all(r.passed for r in report.http_results)
        if pytest_runner:
            assert report.pytest_result.passed, report.pytest_result.stdout
        run_ids.append(report.lifecycle["run_id"])
        response = httpx.get(
            mock_url + "/isolated/products", headers={"X-Req2Test-Run": run_ids[-1]}
        )
        assert response.status_code == 404
    assert run_ids[0] != run_ids[1]


def test_request_timeout_still_cleans_and_blocks_late_write(mock_url):
    spec = HttpTestSpec(
        case_id="timeout",
        name="timeout",
        method="POST",
        path="/isolated/products",
        query={"delay": 1},
        json_body=PRODUCT,
        expected_status=201,
    )
    config = ExecutionConfig(
        enabled=True,
        base_url=mock_url,
        api_specs=[spec],
        mock_isolation=True,
        request_timeout_seconds=0.5,
    )
    report = execute(config)
    assert report.http_results[0].timed_out and not report.pytest_result.passed
    assert report.lifecycle["cleanup"] == "passed"
    time.sleep(0.6)
    assert (
        httpx.get(
            mock_url + "/isolated/products", headers={"X-Req2Test-Run": report.lifecycle["run_id"]}
        ).status_code
        == 404
    )
    assert ET.fromstring(to_junit_xml(report.model_dump())).attrib["errors"] == "2"


def test_seed_and_assertion_failure_still_cleanup(mock_url):
    spec = HttpTestSpec(
        case_id="seed",
        name="seed",
        path="/isolated/products",
        assertions=[{"path": "/items", "op": "length", "expected": 2}],
    )
    report = execute(
        ExecutionConfig(
            enabled=True,
            base_url=mock_url,
            api_specs=[spec],
            mock_isolation=True,
            mock_seed=[PRODUCT],
        )
    )
    assert not report.http_results[0].passed
    assert report.lifecycle["setup"] == "passed" and report.lifecycle["cleanup"] == "passed"


@pytest.mark.parametrize(
    "url",
    [
        "https://example.com",
        "http://localhost",
        "http://127.0.0.1/proxy",
        "http://127.0.0.1?next=https://example.com",
    ],
)
def test_cleanup_never_targets_external_or_proxy_paths(url, monkeypatch):
    monkeypatch.setenv("REQ2TEST_ALLOW_REMOTE_EXECUTION", "true")
    with pytest.raises(ValueError):
        validate_mock_target(url)


def test_cleanup_requires_explicit_test_opt_in(monkeypatch):
    monkeypatch.delenv("REQ2TEST_ENABLE_MOCK_LIFECYCLE")
    with pytest.raises(ValueError):
        validate_mock_target("http://127.0.0.1")


def test_junit_missing_evidence_never_becomes_green():
    report = {
        "executable_cases": [{"case_id": "missing"}],
        "pytest_result": {"passed": False, "exit_code": 124, "case_results": []},
    }
    root = ET.fromstring(to_junit_xml(report))
    assert root.attrib["errors"] == "1"
    root = ET.fromstring(to_junit_xml({"summary": {"status": "disabled"}}))
    assert root.attrib["skipped"] == "1"


def test_prepare_failure_never_executes_and_cleanup_failure_is_reported(mock_url, monkeypatch):
    from req2test.mock_lifecycle import MockLifecycle

    spec = HttpTestSpec(case_id="one", name="one", path="/products")
    report = execute(
        ExecutionConfig(
            enabled=True,
            base_url=mock_url,
            api_specs=[spec],
            mock_isolation=True,
            mock_seed=[{"invalid": True}],
        )
    )
    assert report.lifecycle["setup"] == "error" and not report.http_results
    assert ET.fromstring(to_junit_xml(report.model_dump())).attrib["errors"] == "1"
    cleanup = MockLifecycle.cleanup

    def simulated_cleanup_failure(self):
        cleanup(self)  # Actually clean test state, then model an unconfirmed cleanup response.
        self.state["cleanup"] = "error"
        self.state["error"] = "Mock cleanup unconfirmed"

    monkeypatch.setattr(MockLifecycle, "cleanup", simulated_cleanup_failure)
    report = execute(
        ExecutionConfig(enabled=True, base_url=mock_url, api_specs=[spec], mock_isolation=True)
    )
    assert report.summary["status"] == "error"
    assert ET.fromstring(to_junit_xml(report.model_dump())).attrib["errors"] == "1"


def test_pytest_hard_timeout_parent_cleanup(mock_url, monkeypatch):
    from req2test.execution_models import PytestExecutionResult
    from req2test.pytest_runner import PytestRunnerTool

    monkeypatch.setattr(
        PytestRunnerTool,
        "invoke",
        lambda *a, **kw: PytestExecutionResult(
            passed=False, exit_code=124, duration_ms=5000, stdout="", timed_out=True
        ),
    )
    spec = HttpTestSpec(case_id="one", name="one", path="/isolated/products")
    report = execute(
        ExecutionConfig(
            enabled=True,
            base_url=mock_url,
            api_specs=[spec],
            mock_isolation=True,
            run_http_tool=False,
        )
    )
    assert report.lifecycle["cleanup"] == "passed"
    assert ET.fromstring(to_junit_xml(report.model_dump())).attrib["errors"] == "1"
