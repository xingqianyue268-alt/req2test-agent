"""Parse explicit HTTP contracts without using regex to delimit JSON values."""

from __future__ import annotations

import json
import re
from typing import Any

from .execution_models import HttpTestSpec

_ENDPOINT = re.compile(
    r"\b(GET|POST|PUT|PATCH|DELETE|HEAD|OPTIONS)\s+(/[A-Za-z0-9_./?=&%{}:\-]+)", re.IGNORECASE
)
_FIELD = re.compile(
    r"(请求体|body|json|响应包含|expected_json|期望响应|请求头|headers?|查询参数|query)\s*[:：=]\s*|(预期状态码|期望状态码|状态码|status|返回码|返回|期望)\s*[:：=]?\s*",
    re.IGNORECASE,
)
_STATUS = {"预期状态码", "期望状态码", "状态码", "status", "返回码", "返回", "期望"}


def _json_value(text: str, offset: int, first_line: int) -> tuple[Any, int]:
    try:

        def invalid_constant(_value):
            raise json.JSONDecodeError("不允许非标准 JSON 数值", text, offset)

        return json.JSONDecoder(parse_constant=invalid_constant).raw_decode(text, offset)
    except json.JSONDecodeError as exc:
        # No raw input in errors: contracts may contain test credentials.
        raise ValueError(
            f"JSON 解析错误：第 {first_line + exc.lineno} 行，第 {exc.colno} 列：{exc.msg}"
        ) from None


def extract_explicit_http_specs(requirement_text: str, limit: int = 6) -> list[HttpTestSpec]:
    lines = requirement_text.splitlines()
    specs = []
    index = 0
    while index < len(lines) and len(specs) < limit:
        endpoint = _ENDPOINT.search(lines[index])
        if not endpoint:
            index += 1
            continue
        text = "\n".join(lines[index:])
        cursor = endpoint.end()
        values: dict[str, Any] = {}
        # A detail must follow this endpoint on its line or on contiguous detail lines.
        while cursor < len(text):
            endline = text.find("\n", cursor)
            if endline == -1:
                endline = len(text)
            marker = _FIELD.search(text, cursor, endline)
            if marker:
                label = (marker[1] or marker[2]).lower()
                if label in _STATUS:
                    number = re.match(r"\d{3}\b", text[marker.end() :])
                    if not number:
                        raise ValueError(
                            f"状态码解析错误：第 {index + text.count(chr(10), 0, cursor) + 1} 行"
                        )
                    values["status"] = int(number[0])
                    cursor = marker.end() + len(number[0])
                else:
                    values[label], cursor = _json_value(text, marker.end(), index)
                    tail_end = text.find("\n", cursor)
                    tail_end = len(text) if tail_end == -1 else tail_end
                    tail = text[cursor:tail_end]
                    if tail.strip() and not _FIELD.match(tail.lstrip()):
                        line = index + text.count("\n", 0, cursor) + 1
                        column = cursor - text.rfind("\n", 0, cursor)
                        raise ValueError(
                            f"JSON 解析错误：第 {line} 行，第 {column} 列：JSON 后存在多余内容"
                        )
                continue
            if text[cursor:endline].strip():
                break
            if endline == len(text):
                cursor = endline
                break
            next_start = endline + 1
            whitespace = len(text[next_start:]) - len(text[next_start:].lstrip(" \t"))
            if not _FIELD.match(text, next_start + whitespace):
                cursor = next_start
                break
            cursor = next_start
        consumed_lines = text.count("\n", 0, cursor)

        def field(*keys, default=None, source=values):
            return next((source[k] for k in keys if k in source), default)

        expected = field("响应包含", "expected_json", "期望响应", default={})
        headers = field("请求头", "header", "headers", default={})
        query = field("查询参数", "query", default={})
        if not all(isinstance(x, dict) for x in (expected, headers, query)):
            raise ValueError(
                f"接口契约第 {index + 1} 行：响应包含、请求头和查询参数必须是 JSON 对象"
            )
        specs.append(
            HttpTestSpec(
                case_id=f"API-{len(specs) + 1:03d}",
                name=f"{endpoint[1].upper()} {endpoint[2]}",
                method=endpoint[1].upper(),
                path=endpoint[2].rstrip("，。；;)"),
                json_body=field("请求体", "body", "json"),
                json_body_present=any(k in values for k in ("请求体", "body", "json")),
                expected_status=values.get("status", 200),
                expected_json_contains=expected,
                headers=headers,
                query=query,
            )
        )
        index += max(1, consumed_lines)
    return specs
