"""Regression tests for API-contract grouping, 422 attribution and demo UI."""

from req2test.config import LLMSettings
from req2test.demo_ui import DEMO_HTML
from req2test.enhanced_nodes import analyse_demo_requirements
from req2test.execution_models import ExecutionConfig, HttpExecutionResult
from req2test.tool_calling import analyse_failures, extract_explicit_http_specs


MULTILINE_CONTRACT = """
# 可执行接口契约
GET /demo-target/health
预期状态码：200
响应包含：{"status":"ok"}

POST /demo-target/echo
请求体：{"message":"hello"}
预期状态码：200
响应包含：{"status":"ok"}
"""


def test_demo_parser_groups_multiline_http_contract():
    requirements = analyse_demo_requirements(MULTILINE_CONTRACT)

    assert len(requirements) == 2
    assert requirements[0].description == "GET /demo-target/health"
    assert requirements[0].acceptance_criteria == [
        "预期状态码：200",
        '响应包含：{"status":"ok"}',
    ]
    assert requirements[1].description == "POST /demo-target/echo"
    assert requirements[1].acceptance_criteria == [
        '请求体：{"message":"hello"}',
        "预期状态码：200",
        '响应包含：{"status":"ok"}',
    ]


def test_execution_planner_reads_multiline_request_body_and_assertions():
    specs = extract_explicit_http_specs(MULTILINE_CONTRACT)

    assert len(specs) == 2
    assert specs[0].method == "GET"
    assert specs[0].expected_status == 200
    assert specs[0].expected_json_contains == {"status": "ok"}
    assert specs[1].method == "POST"
    assert specs[1].json_body == {"message": "hello"}
    assert specs[1].expected_status == 200
    assert specs[1].expected_json_contains == {"status": "ok"}


def test_422_is_classified_as_contract_mismatch_when_validation_evidence_is_present():
    failed = HttpExecutionResult(
        case_id="API-422",
        name="POST echo",
        method="POST",
        url="http://api:8000/demo-target/echo",
        passed=False,
        status_code=422,
        expected_status=200,
        failures=[
            "状态码不一致：期望 200，实际 422",
            "请求数据校验未通过：可能缺少必填请求体/参数，或字段类型不符合接口契约",
        ],
    )

    analyses, warnings = analyse_failures(
        [failed],
        LLMSettings(mode="demo"),
        ExecutionConfig(enabled=True, base_url="http://api:8000"),
    )

    assert warnings == []
    assert analyses[0].category == "contract_mismatch"
    assert "接口契约" in analyses[0].suggestion


def test_demo_ui_contains_readable_execution_dashboard_and_raw_json_fallback():
    assert "执行结果" in DEMO_HTML
    assert "HTTP 用例" in DEMO_HTML
    assert "失败归因" in DEMO_HTML
    assert "查看原始 JSON" in DEMO_HTML
    assert "载入全通过 Demo" in DEMO_HTML
    assert "载入失败归因 Demo" in DEMO_HTML
