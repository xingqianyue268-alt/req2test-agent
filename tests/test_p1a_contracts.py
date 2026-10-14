"""Regression-first tests for status expectations and JSON contract parsing."""

import json

import httpx
import pytest

from req2test.config import LLMSettings
from req2test.execution_models import ExecutionConfig, HttpTestSpec
from req2test.http_tool import HttpApiTestTool
from req2test.models import ReviewReport, WorkflowResult
from req2test.tool_calling import execute_with_tools, extract_explicit_http_specs


@pytest.mark.parametrize(
    "expected,actual,passed",
    [
        (422, 422, True),
        (200, 422, False),
        (401, 401, True),
        (200, 401, False),
        (403, 403, True),
        (404, 404, True),
        (500, 500, True),
        (200, 500, False),
    ],
)
def test_status_expectation_is_authoritative(monkeypatch, expected, actual, passed):
    client = httpx.Client
    monkeypatch.setattr(
        httpx,
        "Client",
        lambda **kw: client(
            transport=httpx.MockTransport(
                lambda _: httpx.Response(actual, json={"detail": "synthetic"})
            ),
            **kw,
        ),
    )
    report = execute_with_tools(
        "local",
        WorkflowResult(
            requirements=[], test_cases=[], review=ReviewReport(score=100, coverage_rate=1)
        ),
        LLMSettings(),
        ExecutionConfig(
            enabled=True,
            base_url="http://localhost",
            run_pytest=False,
            api_specs=[HttpTestSpec(case_id="A", name="A", path="/", expected_status=expected)],
        ),
    )
    assert report.http_results[0].passed is passed
    assert bool(report.failure_analysis) is (not passed)
    if passed:
        assert report.failure_analysis_v2["summary"]["failure_count"] == 0


@pytest.mark.parametrize(
    "body",
    [
        {"user": {"name": 'a "quote"', "flags": [True, None, False], "address": {"city": "测试"}}},
        [{"id": 1}, {"id": 2}],
        True,
        None,
        "escaped\\line\ntext",
    ],
)
def test_multiline_json_contract_uses_standard_decoder(body):
    text = (
        "POST /items\n请求体："
        + json.dumps(body, ensure_ascii=False, indent=2)
        + '\n预期状态码：201\n响应包含：{"data":{"items":[{"ok":true}]}}\n\nGET /health'
    )
    specs = extract_explicit_http_specs(text)
    assert len(specs) == 2
    assert specs[0].json_body == body
    assert specs[0].expected_status == 201
    assert specs[0].expected_json_contains == {"data": {"items": [{"ok": True}]}}


@pytest.mark.parametrize(
    "body", ['{"user": {"name": }}', '{"a": 1,}', "[1,2", '{\n"a":true,\n}', "not-json"]
)
def test_malformed_json_is_not_silently_ignored(body):
    with pytest.raises(ValueError, match=r"JSON.*行.*列"):
        extract_explicit_http_specs("POST /items\n请求体：" + body)


def test_json_embedded_method_does_not_create_endpoint():
    specs = extract_explicit_http_specs(
        'POST /items\nbody: {\n"note": "GET /not-an-endpoint",\n"nested": {"expected_json": "literal"}\n}\nstatus: 201\nGET /health'
    )
    assert [s.path for s in specs] == ["/items", "/health"]
    assert specs[0].json_body["note"] == "GET /not-an-endpoint"


@pytest.mark.parametrize(
    "text", ["GET /test 返回422", "GET /test status 422", "GET /test\n期望状态码422"]
)
def test_legacy_status_without_colon(text):
    assert extract_explicit_http_specs(text)[0].expected_status == 422


@pytest.mark.parametrize("value", ["{} garbage", "truefalse", "123.4.5", "[] }"])
def test_json_trailing_garbage_is_rejected(value):
    with pytest.raises(ValueError, match=r"JSON.*行.*列"):
        extract_explicit_http_specs("POST /test\nbody: " + value)


def test_explicit_json_null_sent_as_null(monkeypatch):
    captured = []
    client = httpx.Client

    def handler(request):
        captured.append(request)
        return httpx.Response(200, json={})

    monkeypatch.setattr(
        httpx, "Client", lambda **kw: client(transport=httpx.MockTransport(handler), **kw)
    )
    spec = extract_explicit_http_specs("POST /test body: null")[0]
    assert HttpApiTestTool("http://localhost").invoke(spec).passed
    assert captured[0].content == b"null"
    assert captured[0].headers["content-type"] == "application/json"


@pytest.mark.parametrize("value", ["NaN", "Infinity", "-Infinity", '{"value":NaN}'])
def test_nonstandard_json_numbers_are_rejected(value):
    with pytest.raises(ValueError, match=r"JSON.*行.*列"):
        extract_explicit_http_specs("POST /test\nbody: " + value)
