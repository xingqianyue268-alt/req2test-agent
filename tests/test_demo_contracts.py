"""Regression tests for API-contract grouping, 422 attribution and demo UI."""

import re

from fastapi.testclient import TestClient

from req2test.config import LLMSettings
from req2test.demo_ui import DEMO_HTML
from req2test.enhanced_nodes import analyse_demo_requirements
from req2test.execution_models import ExecutionConfig, HttpExecutionResult
from req2test.tool_calling import analyse_failures, extract_explicit_http_specs
from req2test.api import app


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


def test_demo_ui_contains_design_execution_dashboard_and_raw_json_fallback():
    for marker in [
        "新建测试任务",
        "生成测试用例",
        "测试用例",
        "需求拆分",
        "AI 评审 &amp; RAG",
        "执行结果",
        "HTTP 用例",
        "失败归因",
        "HTTP Tool",
        "Pytest Runner",
        "失败分析",
        "原始 JSON",
        "API 全通过示例",
        "失败归因示例",
    ]:
        assert marker in DEMO_HTML


def test_failure_v2_demo_target_fixtures_are_local_and_deterministic():
    client = TestClient(app)
    assert client.get("/demo-target/protected").status_code == 401
    upstream = client.get("/demo-target/upstream-error")
    assert upstream.status_code == 500
    assert upstream.json()["detail"] == "Demo upstream service failure"
    delayed = client.get("/demo-target/timeout?delay_seconds=0.6")
    assert delayed.status_code == 200
    assert delayed.json()["delay_seconds"] == 0.6


def _javascript_template(name: str) -> str:
    match = re.search(rf"const {name}=`(.*?)`;", DEMO_HTML, re.DOTALL)
    assert match is not None, f"missing JavaScript template: {name}"
    return match.group(1)


def test_failure_v2_demo_selectors_expose_all_real_fixture_scenarios():
    selectors = {
        "contract": "422 契约错误",
        "timeout": "超时",
        "authentication": "401 认证失败",
        "upstream": "500 上游错误",
    }

    for kind, label in selectors.items():
        assert f'data-failure-demo="{kind}"' in DEMO_HTML
        assert f"loadFailureDemo('{kind}')" in DEMO_HTML
        assert label in DEMO_HTML


def test_failure_v2_demo_requirements_and_execution_profiles_do_not_cross():
    pass_demo = _javascript_template("PASS_DEMO")
    contract = _javascript_template("CONTRACT_DEMO")
    timeout = _javascript_template("TIMEOUT_DEMO")
    authentication = _javascript_template("AUTHENTICATION_DEMO")
    upstream = _javascript_template("UPSTREAM_DEMO")

    assert '请求体：{"message":"hello"}' in pass_demo
    assert "/demo-target/health" in pass_demo
    assert "/demo-target/echo" in pass_demo
    assert all(path not in pass_demo for path in ("/timeout", "/protected", "/upstream-error"))

    assert "/demo-target/echo" in contract
    assert "请求体：" not in contract
    assert all(path not in contract for path in ("/timeout", "/protected", "/upstream-error"))

    assert "/demo-target/timeout?delay_seconds=1.25" in timeout
    assert "/demo-target/protected" in authentication
    assert "/demo-target/upstream-error" in upstream
    assert "/protected" not in timeout and "/upstream-error" not in timeout
    assert "/timeout" not in authentication and "/upstream-error" not in authentication
    assert "/timeout" not in upstream and "/protected" not in upstream

    assert "timeout:{requirement:TIMEOUT_DEMO,request_timeout_seconds:0.5,expected_category:'timeout'" in DEMO_HTML
    assert "contract:{requirement:CONTRACT_DEMO,request_timeout_seconds:8.0,expected_category:'contract_mismatch'" in DEMO_HTML
    assert "authentication:{requirement:AUTHENTICATION_DEMO,request_timeout_seconds:8.0,expected_category:'authentication_error'" in DEMO_HTML
    assert "upstream:{requirement:UPSTREAM_DEMO,request_timeout_seconds:8.0,expected_category:'upstream_api_error'" in DEMO_HTML
    assert "baseUrl').value='http://api:8000'" in DEMO_HTML
    assert "run_http_tool:true,run_pytest:true" in DEMO_HTML
    assert "request_timeout_seconds:activeExecutionConfig.request_timeout_seconds" in DEMO_HTML
