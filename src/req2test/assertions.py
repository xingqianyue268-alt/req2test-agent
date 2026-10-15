"""One assertion evaluator for HTTP and generated pytest; JSON Pointer only."""

from __future__ import annotations

from typing import Any

from .execution_models import AssertionOutcome, HttpTestSpec
from .schema_assertions import schema_failures
from .security.redaction import is_sensitive_key, redact_sensitive

_MISSING = object()


def json_contains(actual: Any, expected: Any, path: str = "$") -> list[str]:
    failures = []
    if isinstance(expected, dict):
        if not isinstance(actual, dict):
            return [f"{path} 期望为对象，但实际为 {type(actual).__name__}"]
        for key, value in expected.items():
            if key not in actual:
                failures.append(f"{path}.{key} 缺失")
            else:
                failures.extend(json_contains(actual[key], value, f"{path}.{key}"))
    elif isinstance(expected, list):
        if not isinstance(actual, list) or len(actual) < len(expected):
            return [f"{path} 数组类型或长度不符"]
        for index, value in enumerate(expected):
            failures.extend(json_contains(actual[index], value, f"{path}[{index}]"))
    elif actual != expected:
        failures.append(f"{path} 值不一致")
    return failures


def _at(payload, pointer):
    current = payload
    for segment in pointer.split("/")[1:] if pointer else []:
        key = segment.replace("~1", "/").replace("~0", "~")
        if isinstance(current, dict) and key in current:
            current = current[key]
        elif (
            isinstance(current, list)
            and key.isdigit()
            and len(key) < 10
            and int(key) < len(current)
        ):
            current = current[int(key)]
        else:
            return _MISSING
    return current


def _kind(value):
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int):
        return "integer"
    if isinstance(value, float):
        return "number"
    if isinstance(value, str):
        return "string"
    return "array" if isinstance(value, list) else "object"


def evaluate_response(spec: HttpTestSpec, response) -> list[AssertionOutcome]:
    outcomes = []

    def add(kind, passed, expected=None, actual=None, path="", message=""):
        sensitive = any(
            is_sensitive_key(part.replace("~1", "/").replace("~0", "~")) for part in path.split("/")
        )
        outcomes.append(
            AssertionOutcome(
                assertion_id=f"A-{len(outcomes) + 1:03d}",
                kind=kind,
                path=path,
                passed=passed,
                expected="***" if sensitive else redact_sensitive(expected),
                actual="***" if sensitive else redact_sensitive(actual),
                message=message if not passed else "",
            )
        )

    status_ok = response.status_code == spec.expected_status
    add(
        "status",
        status_ok,
        spec.expected_status,
        response.status_code,
        message=f"状态码不一致：期望 {spec.expected_status}，实际 {response.status_code}",
    )
    if response.status_code == 422 and not status_ok:
        add(
            "validation",
            False,
            message="请求数据校验未通过：可能缺少必填请求体/参数，或字段类型不符合接口契约",
        )
    needs_json = bool(
        spec.expected_json_contains or spec.assertions or spec.expected_json_schema is not None
    )
    if needs_json:
        try:
            payload = response.json()
        except ValueError:
            add("json", False, message="响应不是有效 JSON，无法执行 JSON 断言")
        else:
            if spec.expected_json_contains:
                failures = json_contains(payload, spec.expected_json_contains)
                add(
                    "json_contains",
                    not failures,
                    spec.expected_json_contains,
                    payload,
                    message="；".join(failures),
                )
            if spec.expected_json_schema is not None:
                try:
                    failures = schema_failures(payload, spec.expected_json_schema)
                except ValueError:
                    failures = ["响应 Schema 无效或包含禁止的引用"]
                add("schema", not failures, message="；".join(failures))
            for assertion in spec.assertions:
                value = _at(payload, assertion.path)
                present = value is not _MISSING
                actual = value if present else "<missing>"
                expected = assertion.expected
                ok = False
                if assertion.op == "exists":
                    expected = expected if isinstance(expected, bool) else True
                    actual = present
                    ok = present == expected
                elif present:
                    if assertion.op == "type":
                        actual = _kind(value)
                        ok = actual == expected or expected == "number" and actual == "integer"
                    elif assertion.op in {"eq", "ne"}:
                        ok = value == expected and _kind(value) == _kind(expected)
                        ok = not ok if assertion.op == "ne" else ok
                    elif assertion.op == "length":
                        actual = (
                            len(value) if isinstance(value, (str, list, dict)) else "<no length>"
                        )
                        ok = actual == expected
                    elif assertion.op in {"min", "max"}:
                        if (
                            isinstance(value, (int, float))
                            and not isinstance(value, bool)
                            and isinstance(expected, (int, float))
                            and not isinstance(expected, bool)
                        ):
                            ok = value >= expected if assertion.op == "min" else value <= expected
                add(
                    assertion.op,
                    ok,
                    expected,
                    actual,
                    assertion.path,
                    f"JSON 路径 {assertion.path or '/'} 的 {assertion.op} 断言失败",
                )
    for expected in spec.expected_text_contains:
        add("text_contains", expected in response.text, message="响应正文缺少期望文本")
    return outcomes
