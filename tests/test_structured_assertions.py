import httpx
import pytest
from pydantic import ValidationError

from req2test.assertions import evaluate_response
from req2test.execution_models import HttpTestSpec, JsonAssertion
from req2test.http_tool import HttpApiTestTool


@pytest.mark.parametrize(
    "path,op,value,passed",
    [
        ("/nested/items/0/n", "eq", 3, True),
        ("/nested/items", "length", 1, True),
        ("/nested/items/0/n", "min", 4, False),
        ("/nested/items/0/n", "max", 3, True),
        ("/bool", "type", "integer", False),
        ("/bool", "eq", 1, False),
        ("/bool", "ne", 1, True),
        ("/nothing", "type", "null", True),
        ("/missing", "exists", False, True),
        ("/missing", "eq", None, False),
        ("/a~1b/~0key", "eq", "escaped", True),
        ("/nested/items/0/n", "type", "number", True),
    ],
)
def test_structured_pointer_assertions(path, op, value, passed):
    response = httpx.Response(
        200,
        json={
            "nested": {"items": [{"n": 3}]},
            "bool": True,
            "nothing": None,
            "a/b": {"~key": "escaped"},
        },
    )
    spec = HttpTestSpec(
        case_id="case",
        name="case",
        path="/",
        assertions=[{"path": path, "op": op, "expected": value}],
    )
    outcomes = evaluate_response(spec, response)
    assert outcomes[-1].passed == passed
    if not passed:
        assert path in outcomes[-1].message


@pytest.mark.parametrize(
    "op,value",
    [
        ("type", "python"),
        ("length", True),
        ("length", -1),
        ("min", True),
        ("max", "4"),
        ("exists", "false"),
    ],
)
def test_invalid_assertion_rejected(op, value):
    with pytest.raises(ValidationError):
        JsonAssertion(op=op, expected=value)


def test_schema_path_and_multiple_failures_do_not_echo_values():
    spec = HttpTestSpec(
        case_id="case",
        name="case",
        path="/",
        expected_json_schema={
            "type": "object",
            "properties": {
                "nested": {"type": "object", "properties": {"count": {"type": "integer"}}}
            },
        },
        assertions=[
            {"path": "/missing", "op": "exists"},
            {"path": "/password", "op": "eq", "expected": "synthetic-private"},
        ],
    )
    outcomes = evaluate_response(
        spec,
        httpx.Response(200, json={"nested": {"count": "wrong"}, "password": "synthetic-secret"}),
    )
    assert len([r for r in outcomes if not r.passed]) == 3
    assert "/nested/count" in outcomes[1].message
    assert "synthetic-" not in str([r.model_dump() for r in outcomes])


def test_bad_row_does_not_abort_collection(monkeypatch):
    def request(self, method, url, **kwargs):
        if kwargs["headers"].get("X-Bad"):
            raise ValueError("unsafe value synthetic-private")
        return httpx.Response(200, json={"ok": True})

    monkeypatch.setattr(httpx.Client, "request", request)
    rows = HttpApiTestTool("http://localhost").invoke_many(
        [
            HttpTestSpec(case_id="bad", name="bad", path="/", headers={"X-Bad": "1"}),
            HttpTestSpec(case_id="next", name="next", path="/"),
        ]
    )
    assert [r.passed for r in rows] == [False, True]
    assert "synthetic-private" not in str(rows)
