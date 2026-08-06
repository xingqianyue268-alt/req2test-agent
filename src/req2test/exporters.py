"""Export workflow results to Markdown, CSV and JSON."""

from __future__ import annotations

import csv
import io

from .models import WorkflowResult


def to_markdown(result: WorkflowResult) -> str:
    lines = [
        "# Req2Test Agent 测试用例",
        "",
        f"- 需求项数量：{len(result.requirements)}",
        f"- 测试用例数量：{len(result.test_cases)}",
        f"- 评审得分：{result.review.score}",
        f"- 需求覆盖率：{result.review.coverage_rate:.0%}",
        "",
    ]
    for case in result.test_cases:
        lines.extend(
            [
                f"## {case.case_id} {case.title}",
                "",
                f"- 模块：{case.module}",
                f"- 优先级：{case.priority}",
                f"- 类型：{case.test_type}",
                f"- 来源需求：{case.source_requirement}",
                f"- 前置条件：{'；'.join(case.preconditions)}",
                "",
                "| 序号 | 输入/操作描述 | 预期结果 |",
                "|---:|---|---|",
            ]
        )
        for step in case.steps:
            action = step.action.replace("|", "\\|")
            expected = step.expected.replace("|", "\\|")
            lines.append(f"| {step.order} | {action} | {expected} |")
        lines.append("")
    return "\n".join(lines)


def to_csv_bytes(result: WorkflowResult) -> bytes:
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(
        [
            "用例编号",
            "模块",
            "用例名称",
            "优先级",
            "测试类型",
            "前置条件",
            "步骤序号",
            "输入/操作描述",
            "预期结果",
            "来源需求",
        ]
    )
    for case in result.test_cases:
        for step in case.steps:
            writer.writerow(
                [
                    case.case_id,
                    case.module,
                    case.title,
                    case.priority,
                    case.test_type,
                    "；".join(case.preconditions),
                    step.order,
                    step.action,
                    step.expected,
                    case.source_requirement,
                ]
            )
    return output.getvalue().encode("utf-8-sig")


def to_json_text(result: WorkflowResult) -> str:
    return result.model_dump_json(indent=2)
