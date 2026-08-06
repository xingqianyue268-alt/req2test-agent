"""LangGraph node implementations."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, TypedDict

from .config import GenerationConfig, LLMSettings
from .llm import build_chat_model, invoke_json
from .models import RequirementItem, ReviewReport, TestCase, TestStep
from .prompts import (
    ANALYST_SYSTEM,
    ANALYST_USER,
    DESIGNER_SYSTEM,
    DESIGNER_USER,
    REVIEWER_SYSTEM,
    REVIEWER_USER,
    REVISER_SYSTEM,
    REVISER_USER,
)
from .retrieval import LocalRuleRetriever


class WorkflowState(TypedDict, total=False):
    requirement_text: str
    llm_settings: dict[str, Any]
    generation_config: dict[str, Any]
    retrieved_context: list[str]
    requirements: list[dict[str, Any]]
    test_cases: list[dict[str, Any]]
    review: dict[str, Any]
    review_iterations: int
    errors: list[str]


def _append_error(state: WorkflowState, message: str) -> list[str]:
    return [*state.get("errors", []), message]


def retrieve_context_node(state: WorkflowState) -> dict[str, Any]:
    knowledge_path = Path(__file__).resolve().parents[2] / "knowledge" / "testing_rules.md"
    if not knowledge_path.exists():
        knowledge_path = Path.cwd() / "knowledge" / "testing_rules.md"
    retriever = LocalRuleRetriever.from_markdown(knowledge_path)
    context = retriever.retrieve(state["requirement_text"], top_k=3)
    return {"retrieved_context": context}


def _demo_analyse(text: str) -> list[RequirementItem]:
    items: list[RequirementItem] = []
    module = "通用模块"
    seen: set[str] = set()

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith("#"):
            module = line.lstrip("#").strip() or module
            continue

        heading_match = re.match(
            r"^(?:第[一二三四五六七八九十\d]+[章节部分]|[一二三四五六七八九十]+、)\s*(.{2,20})$",
            line,
        )
        if heading_match and len(line) <= 30 and not any(
            verb in line for verb in ("可以", "支持", "查看", "新增", "修改", "删除", "查询", "登录")
        ):
            module = heading_match.group(1).strip("：: ") or module
            continue

        cleaned = re.sub(r"^(?:[-*•]|\d+[.)、．]|[（(][一二三四五六七八九十\d]+[)）])\s*", "", line)
        cleaned = cleaned.strip()
        if len(cleaned) < 8 or cleaned in seen:
            continue
        seen.add(cleaned)
        items.append(
            RequirementItem(
                requirement_id=f"REQ-{len(items) + 1:03d}",
                module=module,
                description=cleaned,
                acceptance_criteria=[],
            )
        )

    if not items and text.strip():
        sentences = re.split(r"[。；;\n]+", text)
        for sentence in sentences:
            sentence = sentence.strip()
            if len(sentence) >= 8:
                items.append(
                    RequirementItem(
                        requirement_id=f"REQ-{len(items) + 1:03d}",
                        description=sentence,
                    )
                )
    return items[:30]


def analyse_requirements_node(state: WorkflowState) -> dict[str, Any]:
    settings = LLMSettings.model_validate(state["llm_settings"])
    if settings.mode == "demo":
        requirements = _demo_analyse(state["requirement_text"])
        return {"requirements": [item.model_dump() for item in requirements]}

    try:
        model = build_chat_model(settings)
        payload = invoke_json(
            model,
            ANALYST_SYSTEM,
            ANALYST_USER.format(requirement_text=state["requirement_text"]),
        )
        requirements = [RequirementItem.model_validate(item) for item in payload]
        return {"requirements": [item.model_dump() for item in requirements]}
    except Exception as exc:  # noqa: BLE001 - fallback is intentional for demo reliability
        requirements = _demo_analyse(state["requirement_text"])
        return {
            "requirements": [item.model_dump() for item in requirements],
            "errors": _append_error(state, f"需求分析模型调用失败，已回退到本地规则：{exc}"),
        }


def _operation_for(description: str) -> tuple[str, str]:
    rules = [
        (("登录", "认证"), "输入有效账号和密码，点击登录", "系统校验通过并进入授权后的页面"),
        (("新增", "添加", "录入", "创建"), "填写符合要求的有效数据并提交", "系统保存数据并展示成功反馈"),
        (("查询", "搜索", "筛选", "检索"), "输入有效查询条件并执行查询", "系统返回符合条件的数据且字段展示完整"),
        (("修改", "编辑", "更新"), "选择一条已有数据，修改可编辑字段并保存", "系统保存修改内容并展示最新数据"),
        (("删除", "移除"), "选择一条允许删除的数据并确认删除", "系统删除目标数据且列表中不再展示该记录"),
        (("导出", "下载"), "设置有效导出条件并执行导出", "系统生成可打开的文件，内容与筛选结果一致"),
        (("上传", "导入"), "选择符合格式要求的文件并提交", "系统完成文件解析并反馈处理结果"),
        (("审核", "审批"), "选择一条待处理数据并提交通过操作", "系统更新审核状态并记录处理结果"),
    ]
    for keywords, action, expected in rules:
        if any(keyword in description for keyword in keywords):
            return action, expected
    return "按照需求描述完成一次有效业务操作并提交", "系统处理成功，页面结果与需求描述一致"


def _negative_operation(description: str) -> tuple[str, str]:
    if any(keyword in description for keyword in ("登录", "认证")):
        return "输入错误密码并点击登录", "系统拒绝登录并给出明确错误提示，不创建登录会话"
    if any(keyword in description for keyword in ("上传", "导入")):
        return "选择不受支持的文件格式并提交", "系统阻止导入并提示允许的文件格式"
    if any(keyword in description for keyword in ("查询", "搜索", "筛选")):
        return "输入不符合字段格式的查询条件并执行查询", "系统提示条件格式错误或返回空结果，不出现异常页面"
    return "缺少一个必填项或输入不符合格式的数据后提交", "系统阻止提交并在对应字段附近给出明确校验提示"


def _edge_operation(description: str) -> tuple[str, str]:
    if any(keyword in description for keyword in ("查询", "搜索", "筛选", "列表")):
        return "使用最小有效条件执行查询，并查看无匹配数据场景", "系统正确展示空状态，不出现残留数据或报错"
    if any(keyword in description for keyword in ("上传", "导入")):
        return "上传接近系统允许大小上限的合法文件", "系统在限制范围内完成处理，并保持页面可响应"
    return "在字段允许范围内输入最小值或最大值并提交", "系统接受边界内数据，保存结果与输入一致"


def _make_case(
    requirement: RequirementItem,
    case_index: int,
    test_type: str,
    action: str,
    expected: str,
) -> TestCase:
    prefix = {"正向": "验证", "异常": "校验", "边界": "边界验证"}[test_type]
    title_desc = requirement.description[:28].rstrip("，。；;：:")
    priority = "P1" if test_type == "正向" else "P2"
    return TestCase(
        case_id=f"TC-{case_index:03d}",
        module=requirement.module,
        title=f"{prefix}{title_desc}",
        priority=priority,
        test_type=test_type,
        preconditions=["测试环境可访问", f"已进入{requirement.module}相关页面"],
        steps=[
            TestStep(
                order=1,
                action=f"定位与“{title_desc}”对应的功能入口",
                expected="页面展示与需求对应的操作入口和必要字段",
            ),
            TestStep(order=2, action=action, expected=expected),
            TestStep(
                order=3,
                action="查看页面提示、数据状态和后续可见结果",
                expected="页面反馈清晰，业务数据状态与本次操作结果一致",
            ),
        ],
        source_requirement=requirement.requirement_id,
        rationale=f"覆盖需求：{requirement.description}",
    )


def _variant_plan(
    requirement: RequirementItem, config: GenerationConfig
) -> list[tuple[str, tuple[str, str]]]:
    description = requirement.description
    explicit_negative = any(
        keyword in description
        for keyword in ("错误", "失败", "无匹配", "查询不到", "阻止", "不支持", "无效")
    )
    explicit_edge = any(
        keyword in description for keyword in ("最大", "最小", "上限", "下限", "边界", "空结果")
    )

    variants: list[tuple[str, tuple[str, str]]] = []
    if explicit_negative and config.include_negative:
        variants.append(("异常", _negative_operation(description)))
    elif explicit_edge and config.include_edge:
        variants.append(("边界", _edge_operation(description)))
    elif config.include_positive:
        variants.append(("正向", _operation_for(description)))
    elif config.include_negative:
        variants.append(("异常", _negative_operation(description)))
    elif config.include_edge:
        variants.append(("边界", _edge_operation(description)))

    if not explicit_negative and config.include_negative:
        variants.append(("异常", _negative_operation(description)))
    if not explicit_edge and config.include_edge:
        variants.append(("边界", _edge_operation(description)))
    return variants


def _demo_design(requirements: list[RequirementItem], config: GenerationConfig) -> list[TestCase]:
    """Generate coverage-first cases, then add supplementary variants.

    This prevents the case limit from spending all slots on the first few
    requirements and leaving later requirements uncovered.
    """

    plans = [(requirement, _variant_plan(requirement, config)) for requirement in requirements]
    cases: list[TestCase] = []

    # First pass: one primary case per requirement.
    for requirement, variants in plans:
        if len(cases) >= config.max_cases:
            return cases
        if not variants:
            continue
        test_type, (action, expected) = variants[0]
        cases.append(_make_case(requirement, len(cases) + 1, test_type, action, expected))

    # Second pass: add abnormal/edge variants in round-robin order.
    extra_index = 1
    while len(cases) < config.max_cases:
        added = False
        for requirement, variants in plans:
            if len(cases) >= config.max_cases:
                break
            if extra_index >= len(variants):
                continue
            test_type, (action, expected) = variants[extra_index]
            cases.append(_make_case(requirement, len(cases) + 1, test_type, action, expected))
            added = True
        if not added:
            break
        extra_index += 1
    return cases


def design_cases_node(state: WorkflowState) -> dict[str, Any]:
    settings = LLMSettings.model_validate(state["llm_settings"])
    config = GenerationConfig.model_validate(state["generation_config"])
    requirements = [RequirementItem.model_validate(item) for item in state.get("requirements", [])]

    if settings.mode == "demo":
        cases = _demo_design(requirements, config)
        return {"test_cases": [case.model_dump() for case in cases]}

    try:
        model = build_chat_model(settings)
        payload = invoke_json(
            model,
            DESIGNER_SYSTEM,
            DESIGNER_USER.format(
                requirements_json=json.dumps(
                    [item.model_dump() for item in requirements], ensure_ascii=False, indent=2
                ),
                context="\n\n".join(state.get("retrieved_context", [])),
                config_json=config.model_dump_json(indent=2),
            ),
        )
        cases = [TestCase.model_validate(item) for item in payload][: config.max_cases]
        return {"test_cases": [case.model_dump() for case in cases]}
    except Exception as exc:  # noqa: BLE001
        cases = _demo_design(requirements, config)
        return {
            "test_cases": [case.model_dump() for case in cases],
            "errors": _append_error(state, f"测试设计模型调用失败，已回退到本地规则：{exc}"),
        }


def _demo_review(requirements: list[RequirementItem], cases: list[TestCase]) -> ReviewReport:
    issues: list[str] = []
    suggestions: list[str] = []
    requirement_ids = {item.requirement_id for item in requirements}
    covered = {case.source_requirement for case in cases if case.source_requirement in requirement_ids}
    coverage_rate = len(covered) / len(requirement_ids) if requirement_ids else 0.0

    completeness_scores: list[float] = []
    titles: set[str] = set()
    for case in cases:
        checks = [
            bool(case.title.strip()),
            bool(case.preconditions),
            len(case.steps) >= 2,
            all(step.action.strip() and step.expected.strip() for step in case.steps),
            bool(case.source_requirement.strip()),
        ]
        completeness_scores.append(sum(checks) / len(checks))
        if case.title in titles:
            issues.append(f"存在重复用例标题：{case.title}")
        titles.add(case.title)

    completeness = sum(completeness_scores) / len(completeness_scores) if cases else 0.0
    score = round(coverage_rate * 55 + completeness * 40 + (5 if cases else 0))
    score = min(100, score)

    if coverage_rate < 1.0:
        missing = sorted(requirement_ids - covered)
        issues.append(f"未覆盖需求：{', '.join(missing)}")
        suggestions.append("为未覆盖需求补充至少一条可执行测试用例")
    if completeness < 1.0:
        issues.append("部分用例字段或步骤不完整")
        suggestions.append("补全前置条件、操作步骤及逐步对应的预期结果")
    if not issues:
        suggestions.append("当前用例结构完整，可在真实项目中补充具体测试数据和环境信息")

    return ReviewReport(
        score=score,
        coverage_rate=round(coverage_rate, 4),
        issues=issues,
        suggestions=suggestions,
    )


def review_cases_node(state: WorkflowState) -> dict[str, Any]:
    settings = LLMSettings.model_validate(state["llm_settings"])
    requirements = [RequirementItem.model_validate(item) for item in state.get("requirements", [])]
    cases = [TestCase.model_validate(item) for item in state.get("test_cases", [])]

    if settings.mode == "demo":
        report = _demo_review(requirements, cases)
        return {"review": report.model_dump()}

    try:
        model = build_chat_model(settings)
        payload = invoke_json(
            model,
            REVIEWER_SYSTEM,
            REVIEWER_USER.format(
                requirements_json=json.dumps(
                    [item.model_dump() for item in requirements], ensure_ascii=False, indent=2
                ),
                cases_json=json.dumps(
                    [item.model_dump() for item in cases], ensure_ascii=False, indent=2
                ),
            ),
        )
        report = ReviewReport.model_validate(payload)
        return {"review": report.model_dump()}
    except Exception as exc:  # noqa: BLE001
        report = _demo_review(requirements, cases)
        return {
            "review": report.model_dump(),
            "errors": _append_error(state, f"评审模型调用失败，已回退到本地规则：{exc}"),
        }


def _demo_revise(cases: list[TestCase]) -> list[TestCase]:
    revised: list[TestCase] = []
    for index, case in enumerate(cases, start=1):
        data = case.model_dump()
        data["case_id"] = f"TC-{index:03d}"
        if not data["preconditions"]:
            data["preconditions"] = ["测试环境可访问", "已准备符合要求的测试账号和数据"]
        if len(data["steps"]) < 2:
            data["steps"] = [
                {
                    "order": 1,
                    "action": "进入目标功能页面并完成需求对应操作",
                    "expected": "系统展示对应操作入口并正确处理请求",
                },
                {
                    "order": 2,
                    "action": "查看处理结果",
                    "expected": "页面提示和数据状态与本次操作一致",
                },
            ]
        revised.append(TestCase.model_validate(data))
    return revised


def revise_cases_node(state: WorkflowState) -> dict[str, Any]:
    settings = LLMSettings.model_validate(state["llm_settings"])
    requirements = [RequirementItem.model_validate(item) for item in state.get("requirements", [])]
    cases = [TestCase.model_validate(item) for item in state.get("test_cases", [])]
    iterations = state.get("review_iterations", 0) + 1

    if settings.mode == "demo":
        revised = _demo_revise(cases)
        return {
            "test_cases": [case.model_dump() for case in revised],
            "review_iterations": iterations,
        }

    try:
        model = build_chat_model(settings)
        payload = invoke_json(
            model,
            REVISER_SYSTEM,
            REVISER_USER.format(
                requirements_json=json.dumps(
                    [item.model_dump() for item in requirements], ensure_ascii=False, indent=2
                ),
                cases_json=json.dumps(
                    [item.model_dump() for item in cases], ensure_ascii=False, indent=2
                ),
                review_json=json.dumps(state.get("review", {}), ensure_ascii=False, indent=2),
            ),
        )
        revised = [TestCase.model_validate(item) for item in payload]
        return {
            "test_cases": [case.model_dump() for case in revised],
            "review_iterations": iterations,
        }
    except Exception as exc:  # noqa: BLE001
        revised = _demo_revise(cases)
        return {
            "test_cases": [case.model_dump() for case in revised],
            "review_iterations": iterations,
            "errors": _append_error(state, f"修订模型调用失败，已回退到本地规则：{exc}"),
        }


def route_after_review(state: WorkflowState) -> str:
    config = GenerationConfig.model_validate(state["generation_config"])
    score = int(state.get("review", {}).get("score", 0))
    iterations = state.get("review_iterations", 0)
    if score < config.min_review_score and iterations < config.max_review_iterations:
        return "revise"
    return "finish"
