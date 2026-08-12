"""Targeted node enhancements used by the production graph.

This module keeps the original node implementation intact and adds a stricter
requirement parser for demo/fallback mode. In particular, an explicit HTTP API
contract is treated as one requirement instead of splitting method/path,
status-code expectation and response assertions into separate requirements.
"""

from __future__ import annotations

import re
from typing import Any

from .config import LLMSettings
from .models import RequirementItem
from .nodes import WorkflowState, analyse_requirements_node as _original_analyse_requirements_node

_HTTP_LINE = re.compile(
    r"^\s*(GET|POST|PUT|PATCH|DELETE|HEAD|OPTIONS)\s+(/[A-Za-z0-9_./?=&%{}:\-]+)",
    flags=re.IGNORECASE,
)
_CONTRACT_DETAIL = re.compile(
    r"^(?:预期状态码|期望状态码|状态码|status|响应包含|期望响应|expected_json|"
    r"请求体|body|json|请求头|headers?|查询参数|query)\s*[:：=]",
    flags=re.IGNORECASE,
)
_HEADING = re.compile(
    r"^(?:第[一二三四五六七八九十\d]+[章节部分]|[一二三四五六七八九十]+、)\s*(.{2,20})$"
)


def _clean_requirement_line(line: str) -> str:
    return re.sub(
        r"^(?:[-*•]|\d+[.)、．]|[（(][一二三四五六七八九十\d]+[)）])\s*",
        "",
        line,
    ).strip()


def _append_item(
    items: list[RequirementItem],
    seen: set[str],
    module: str,
    description: str,
    acceptance_criteria: list[str] | None = None,
) -> None:
    description = description.strip()
    if len(description) < 4 or description in seen:
        return
    seen.add(description)
    items.append(
        RequirementItem(
            requirement_id=f"REQ-{len(items) + 1:03d}",
            module=module,
            description=description,
            acceptance_criteria=acceptance_criteria or [],
        )
    )


def analyse_demo_requirements(text: str) -> list[RequirementItem]:
    """Parse demo requirements while preserving API contract boundaries."""

    lines = text.splitlines()
    items: list[RequirementItem] = []
    seen: set[str] = set()
    module = "通用模块"
    index = 0

    while index < len(lines):
        line = lines[index].strip()
        if not line:
            index += 1
            continue

        if line.startswith("#"):
            module = line.lstrip("#").strip() or module
            index += 1
            continue

        heading_match = _HEADING.match(line)
        if heading_match and len(line) <= 30 and not any(
            verb in line for verb in ("可以", "支持", "查看", "新增", "修改", "删除", "查询", "登录")
        ):
            module = heading_match.group(1).strip("：: ") or module
            index += 1
            continue

        http_match = _HTTP_LINE.match(line)
        if http_match:
            method = http_match.group(1).upper()
            path = http_match.group(2).rstrip("，。；;)")
            criteria: list[str] = []
            cursor = index + 1
            while cursor < len(lines):
                detail = lines[cursor].strip()
                if not detail:
                    break
                if detail.startswith("#") or _HTTP_LINE.match(detail):
                    break
                if not _CONTRACT_DETAIL.match(detail):
                    break
                criteria.append(detail)
                cursor += 1

            _append_item(
                items,
                seen,
                module,
                f"{method} {path}",
                acceptance_criteria=criteria,
            )
            index = cursor
            continue

        cleaned = _clean_requirement_line(line)
        if len(cleaned) >= 8:
            _append_item(items, seen, module, cleaned)
        index += 1

    if not items and text.strip():
        for sentence in re.split(r"[。；;\n]+", text):
            sentence = sentence.strip()
            if len(sentence) >= 8:
                _append_item(items, seen, "通用模块", sentence)

    return items[:30]


def analyse_requirements_node(state: WorkflowState) -> dict[str, Any]:
    """Use the contract-aware parser in demo mode and model-fallback mode."""

    settings = LLMSettings.model_validate(state["llm_settings"])
    if settings.mode == "demo":
        requirements = analyse_demo_requirements(state["requirement_text"])
        return {"requirements": [item.model_dump() for item in requirements]}

    result = _original_analyse_requirements_node(state)
    errors = result.get("errors", [])
    if any("需求分析模型调用失败" in str(error) for error in errors):
        requirements = analyse_demo_requirements(state["requirement_text"])
        result["requirements"] = [item.model_dump() for item in requirements]
    return result
