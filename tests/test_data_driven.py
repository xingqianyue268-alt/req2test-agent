"""P1-B regression-first data identity and independent assertions."""

import base64
import json

import httpx
import pytest

from req2test.data_driven import DatasetUpload, expand_dataset
from req2test.execution_models import HttpTestSpec
from req2test.http_tool import HttpApiTestTool


def upload(rows):
    return DatasetUpload(
        filename="login.json", content_base64=base64.b64encode(json.dumps(rows).encode()).decode()
    )


def test_json_rows_keep_identity_expected_status_and_source():
    template = HttpTestSpec(case_id="LOGIN", name="login", method="POST", path="/login")
    cases = expand_dataset(
        template,
        upload(
            [
                {
                    "id": "valid",
                    "json_body": {"username": "demo", "password": "demo"},
                    "expected_status": 200,
                },
                {"id": "missing", "json_body": {}, "expected_status": 422},
                {"id": "invalid", "json_body": {"username": False}, "expected_status": 422},
            ]
        ),
    )
    assert [c.case_id for c in cases] == ["LOGIN::valid", "LOGIN::missing", "LOGIN::invalid"]
    assert [c.data_id for c in cases] == ["valid", "missing", "invalid"]
    assert cases[1].source == "login.json:2"
    assert cases[1].expected_status == 422


@pytest.mark.parametrize(
    "rows",
    [[{"id": "dup"}, {"id": "dup"}], [{"json_body": {}}], [{"id": "one", "unknown": True}], []],
)
def test_invalid_dataset_rejected(rows):
    with pytest.raises(ValueError):
        expand_dataset(HttpTestSpec(case_id="A", name="a", path="/"), upload(rows))


def test_csv_complex_json_and_error_location():
    source = (
        'id,json_body,expected_status\nvalid,"{""user"":{""name"":""demo""}}",200\nmissing,{},422\n'
    )
    data = DatasetUpload(
        filename="data.csv", content_base64=base64.b64encode(source.encode()).decode()
    )
    result = expand_dataset(HttpTestSpec(case_id="A", name="a", path="/"), data)
    assert result[0].json_body == {"user": {"name": "demo"}}
    assert result[1].expected_status == 422
    data.content_base64 = base64.b64encode(b"id,json_body\nbad,{broken\n").decode()
    with pytest.raises(ValueError, match="2"):
        expand_dataset(HttpTestSpec(case_id="A", name="a", path="/"), data)


def test_multiple_assertions_aggregate_and_mask_leaf_secrets(monkeypatch):
    original = httpx.Client
    monkeypatch.setattr(
        httpx,
        "Client",
        lambda **kw: original(
            transport=httpx.MockTransport(
                lambda _: httpx.Response(
                    422, json={"data": {"count": 2, "items": [1, 2], "password": "SYNTHETIC_LEAF"}}
                )
            ),
            **kw,
        ),
    )
    spec = HttpTestSpec(
        case_id="A",
        name="a",
        path="/",
        expected_status=422,
        assertions=[
            {"path": "/data/count", "op": "type", "expected": "integer"},
            {"path": "/data/items", "op": "length", "expected": 3},
            {"path": "/data/missing", "op": "exists"},
            {"path": "/data/password", "op": "eq", "expected": "OTHER_SYNTHETIC_LEAF"},
        ],
    )
    result = HttpApiTestTool("http://localhost").invoke(spec)
    assert not result.passed
    assert len([a for a in result.assertions if not a.passed]) == 3
    assert "SYNTHETIC_LEAF" not in result.model_dump_json()
    assert any(a.path == "/data/items" and a.actual == 2 for a in result.assertions)


def test_contract_dataset_selects_matching_error_response_schema():
    from pathlib import Path

    from req2test.openapi_import import ContractPlan, compile_plan

    file = Path(__file__).resolve().parents[1] / "examples/openapi/synthetic-shop.json"
    plan = ContractPlan(
        filename=file.name,
        content_base64=base64.b64encode(file.read_bytes()).decode(),
        selected_operations=["POST /login"],
        base_url="http://localhost",
        datasets={
            "POST /login": upload([{"id": "missing", "json_body": {}, "expected_status": 422}])
        },
    )
    spec = compile_plan(plan).api_specs[0]
    assert spec.expected_status == 422 and spec.data_id == "missing"
    from req2test.assertions import evaluate_response

    assert all(r.passed for r in evaluate_response(spec, httpx.Response(422, json={"detail": []})))


def test_duplicate_json_and_error_locations_rejected():
    template = HttpTestSpec(case_id="a", name="a", path="/")
    for source, match in [('[{"id":"a","id":"b"}]', "重复"), ('[\n{"id":}]', "第 2 行")]:
        data = DatasetUpload(
            filename="data.json", content_base64=base64.b64encode(source.encode()).decode()
        )
        with pytest.raises(ValueError, match=match):
            expand_dataset(template, data)
