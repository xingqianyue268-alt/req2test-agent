"""Tool-calling execution layer for generated Req2Test cases.

The planner can use an OpenAI-compatible model to convert explicitly documented
API contracts into structured tool calls. Demo mode uses a deterministic parser.
The dispatcher then invokes the HTTP API tool and Pytest runner, and finally
produces failure attribution from the real execution results.
"""

from __future__ import annotations

import json
import re
import time
from typing import Any

from .config import LLMSettings
from .execution_models import (
    ExecutionConfig,
    ExecutionReport,
    FailureAnalysis,
    HttpExecutionResult,
    HttpTestSpec,
    ToolInvocation,
)
from .http_tool import HttpApiTestTool
from .diagnostics.evidence import EvidenceCollector, TraceContext
from .llm import build_chat_model, invoke_json
from .models import WorkflowResult
from .pytest_runner import PytestRunnerTool


_PLANNER_SYSTEM = """你是软件测试执行规划智能体。你的任务是把需求中明确出现的 HTTP API 信息转换为可执行测试规格。
严格规则：
1. 只能使用需求文本里明确出现的 HTTP 方法和路径，绝对不能猜测或编造接口路径。
2. 如果需求没有明确接口方法或路径，返回空数组 []。
3. 根据需求中明确给出的状态码、请求体和响应约束填写字段；缺失时可使用最保守的默认值 expected_status=200，但不要凭空补业务字段。
4. path 必须是以 / 开头的相对路径，不得输出完整 URL。
5. 输出必须是 JSON 数组，不要解释。
每项字段：case_id,name,method,path,headers,query,json_body,expected_status,expected_json_contains,expected_text_contains。"""


_FAILURE_SYSTEM = """你是软件测试失败归因智能体。根据真实 HTTP 执行结果判断最可能的失败类别和建议。
只能基于输入证据，不要虚构服务端日志或内部实现。
category 只能是 connectivity, timeout, authentication, route_or_test_data, server_error, contract_mismatch, assertion_failure, unknown。
输出 JSON 数组，每项字段：case_id,category,probable_cause,evidence,suggestion。"""

_HTTP_PATTERN = re.compile(
    r"\b(GET|POST|PUT|PATCH|DELETE|HEAD|OPTIONS)\s+(/[A-Za-z0-9_./?=&%{}:\-]+)",
    flags=re.IGNORECASE,
)
_CONTRACT_DETAIL_PATTERN = re.compile(
    r"^(?:预期状态码|期望状态码|状态码|status|响应包含|期望响应|expected_json|"
    r"请求体|body|json|请求头|headers?|查询参数|query)\s*[:：=]",
    flags=re.IGNORECASE,
)


def _extract_json_object_after(label: str, text: str) -> Any | None:
    marker = re.search(rf"{label}\s*[:：]\s*(\{{.*?\}}|\[.*?\])(?:\s|$)", text, flags=re.IGNORECASE)
    if not marker:
        return None
    try:
        return json.loads(marker.group(1))
    except json.JSONDecodeError:
        return None


def _collect_contract_block(lines: list[str], start: int) -> tuple[str, int]:
    """Collect one endpoint line plus contiguous explicit contract-detail lines."""

    block = [lines[start].strip()]
    cursor = start + 1
    while cursor < len(lines):
        detail = lines[cursor].strip()
        if not detail or detail.startswith("#") or _HTTP_PATTERN.search(detail):
            break
        if not _CONTRACT_DETAIL_PATTERN.match(detail):
            break
        block.append(detail)
        cursor += 1
    return " ".join(block), cursor


def extract_explicit_http_specs(requirement_text: str, limit: int = 6) -> list[HttpTestSpec]:
    """Extract only endpoints explicitly written in the requirement text.

    Contract details may be placed on the endpoint line or on following lines,
    for example status code, JSON request body and expected JSON subset.
    """

    specs: list[HttpTestSpec] = []
    lines = requirement_text.splitlines()
    index = 0
    while index < len(lines):
        line = lines[index].strip()
        if not line:
            index += 1
            continue
        match = _HTTP_PATTERN.search(line)
        if not match:
            index += 1
            continue

        method = match.group(1).upper()
        path = match.group(2).rstrip("，。；;)")
        contract_text, next_index = _collect_contract_block(lines, index)

        expected_status = 200
        status_match = re.search(
            r"(?:status|状态码|期望状态码|预期状态码|返回码|返回|期望)\s*[:：=]?\s*(\d{3})",
            contract_text,
            flags=re.IGNORECASE,
        )
        if status_match:
            expected_status = int(status_match.group(1))

        json_body = _extract_json_object_after(r"(?:请求体|body|json)", contract_text)
        expected_json = _extract_json_object_after(
            r"(?:响应包含|expected_json|期望响应)", contract_text
        )
        if not isinstance(expected_json, dict):
            expected_json = {}

        specs.append(
            HttpTestSpec(
                case_id=f"API-{len(specs) + 1:03d}",
                name=f"{method} {path}",
                method=method,
                path=path,
                json_body=json_body,
                expected_status=expected_status,
                expected_json_contains=expected_json,
            )
        )
        if len(specs) >= limit:
            break
        index = max(next_index, index + 1)
    return specs


def _workflow_context(result: WorkflowResult) -> str:
    cases = [
        {
            "case_id": case.case_id,
            "title": case.title,
            "source_requirement": case.source_requirement,
            "steps": [
                {"action": step.action, "expected": step.expected}
                for step in case.steps
            ],
        }
        for case in result.test_cases[:12]
    ]
    return json.dumps(cases, ensure_ascii=False, indent=2)


def plan_executable_tests(
    requirement_text: str,
    workflow_result: WorkflowResult,
    llm_settings: LLMSettings,
    config: ExecutionConfig,
) -> tuple[list[HttpTestSpec], str, list[str]]:
    warnings: list[str] = []
    if config.api_specs:
        return config.api_specs[: config.max_executable_cases], "provided_specs", warnings

    fallback_specs = extract_explicit_http_specs(
        requirement_text,
        limit=config.max_executable_cases,
    )

    if llm_settings.mode != "openai_compatible" or not config.use_llm_planner:
        return fallback_specs, "deterministic", warnings

    try:
        model = build_chat_model(llm_settings)
        user_prompt = (
            "需求文本：\n"
            f"{requirement_text}\n\n"
            "已生成的功能测试用例，仅用于理解预期行为：\n"
            f"{_workflow_context(workflow_result)}"
        )
        payload = invoke_json(model, _PLANNER_SYSTEM, user_prompt)
        if not isinstance(payload, list):
            raise ValueError("执行规划模型没有返回 JSON 数组")
        specs = [HttpTestSpec.model_validate(item) for item in payload]
        explicit_pairs = {(item.method, item.path) for item in fallback_specs}
        filtered = [item for item in specs if (item.method, item.path) in explicit_pairs]
        if len(filtered) != len(specs):
            warnings.append("执行规划模型输出了需求中未明确出现的接口，已自动丢弃。")
        return filtered[: config.max_executable_cases], "llm_tool_planner", warnings
    except Exception as exc:  # noqa: BLE001
        warnings.append(f"LLM 执行规划失败，已回退到显式接口解析：{exc}")
        return fallback_specs, "deterministic_fallback", warnings


def _heuristic_failure_analysis(result: HttpExecutionResult) -> FailureAnalysis:
    evidence = [*result.failures]
    if result.error:
        evidence.append(result.error)
    error_text = " ".join(evidence).lower()

    if "timeout" in error_text or "超时" in error_text:
        return FailureAnalysis(
            case_id=result.case_id,
            category="timeout",
            probable_cause="目标接口在测试超时时间内没有完成响应。",
            evidence=evidence,
            suggestion="检查接口处理耗时、下游依赖和测试超时配置，并结合服务端日志定位慢点。",
        )
    if result.error and result.status_code is None:
        return FailureAnalysis(
            case_id=result.case_id,
            category="connectivity",
            probable_cause="测试客户端未能与目标服务建立稳定 HTTP 连接。",
            evidence=evidence,
            suggestion="确认 base_url、端口、网络连通性、DNS/代理配置以及服务是否已经启动。",
        )
    if result.status_code in {401, 403}:
        return FailureAnalysis(
            case_id=result.case_id,
            category="authentication",
            probable_cause="接口返回认证或权限拒绝，测试凭证可能缺失、失效或权限不足。",
            evidence=evidence,
            suggestion="核对 Authorization/Cookie 等认证信息及测试账号权限，不要在日志中输出真实密钥。",
        )
    if result.status_code == 404:
        return FailureAnalysis(
            case_id=result.case_id,
            category="route_or_test_data",
            probable_cause="接口路径、资源标识或测试数据可能与当前环境不一致。",
            evidence=evidence,
            suggestion="核对环境路由、API 版本、资源 ID 和前置测试数据。",
        )
    if result.status_code == 422:
        return FailureAnalysis(
            case_id=result.case_id,
            category="contract_mismatch",
            probable_cause="请求已到达目标接口，但请求体或参数未通过服务端契约校验。",
            evidence=evidence,
            suggestion="核对接口契约中的必填字段、字段类型、请求体格式和测试数据后重新执行。",
        )
    if result.status_code is not None and result.status_code >= 500:
        return FailureAnalysis(
            case_id=result.case_id,
            category="server_error",
            probable_cause="目标服务返回 5xx，问题更可能位于服务端处理或其下游依赖。",
            evidence=evidence,
            suggestion="结合请求时间点检查服务端异常日志、依赖服务和数据库状态。",
        )
    if any(keyword in error_text for keyword in ("json", "缺少", "值不一致", "响应正文")):
        return FailureAnalysis(
            case_id=result.case_id,
            category="contract_mismatch",
            probable_cause="实际响应结构或关键字段与测试期望不一致。",
            evidence=evidence,
            suggestion="核对接口契约、字段类型、版本变更及用例期望是否仍然有效。",
        )
    if result.failures:
        return FailureAnalysis(
            case_id=result.case_id,
            category="assertion_failure",
            probable_cause="接口可访问，但实际结果没有满足测试断言。",
            evidence=evidence,
            suggestion="比较实际响应和需求验收标准，确认是产品缺陷还是测试期望需要更新。",
        )
    return FailureAnalysis(
        case_id=result.case_id,
        category="unknown",
        probable_cause="当前执行证据不足以确定失败原因。",
        evidence=evidence,
        suggestion="补充请求上下文、服务端日志和稳定复现步骤后再次分析。",
    )


def analyse_failures(
    results: list[HttpExecutionResult],
    llm_settings: LLMSettings,
    config: ExecutionConfig,
) -> tuple[list[FailureAnalysis], list[str]]:
    failed = [result for result in results if not result.passed]
    if not failed:
        return [], []

    heuristic = [_heuristic_failure_analysis(result) for result in failed]
    if llm_settings.mode != "openai_compatible" or not config.use_llm_failure_analysis:
        return heuristic, []

    safe_payload = [
        {
            "case_id": result.case_id,
            "method": result.method,
            "url_path": re.sub(r"^https?://[^/]+", "", result.url),
            "status_code": result.status_code,
            "expected_status": result.expected_status,
            "failures": result.failures,
            "error": result.error,
        }
        for result in failed
    ]
    try:
        model = build_chat_model(llm_settings)
        payload = invoke_json(
            model,
            _FAILURE_SYSTEM,
            json.dumps(safe_payload, ensure_ascii=False, indent=2),
        )
        analyses = [FailureAnalysis.model_validate(item) for item in payload]
        known_ids = {result.case_id for result in failed}
        analyses = [item for item in analyses if item.case_id in known_ids]
        if analyses:
            return analyses, []
    except Exception as exc:  # noqa: BLE001
        return heuristic, [f"LLM 失败归因不可用，已使用规则归因：{exc}"]
    return heuristic, ["LLM 失败归因没有返回有效结果，已使用规则归因。"]


def execute_with_tools(
    requirement_text: str,
    workflow_result: WorkflowResult,
    llm_settings: LLMSettings,
    config: ExecutionConfig,
    trace_context: TraceContext | None = None,
    initial_evidence: list[dict[str, Any]] | None = None,
) -> ExecutionReport:
    """Plan executable checks, dispatch tools, and analyse real execution failures."""

    context = trace_context or TraceContext.for_task("standalone-" + str(time.time_ns()))
    collector = EvidenceCollector(context)
    report = ExecutionReport(
        enabled=config.enabled,
        trace_id=context.trace_id,
        diagnostic_evidence=list(initial_evidence or []),
    )
    if not config.enabled:
        report.summary = {"status": "disabled"}
        return report
    if not config.base_url:
        report.warnings.append("已开启执行阶段，但未提供 base_url，因此跳过真实接口执行。")
        report.summary = {"status": "skipped", "reason": "missing_base_url"}
        return report

    specs, planner_mode, warnings = plan_executable_tests(
        requirement_text,
        workflow_result,
        llm_settings,
        config,
    )
    report.planner_mode = planner_mode
    report.executable_cases = specs
    report.warnings.extend(warnings)

    if not specs:
        report.warnings.append(
            "需求中没有发现可安全执行的显式 HTTP 方法/路径。可在 execution_config.api_specs 中提供结构化接口用例。"
        )
        report.summary = {"status": "skipped", "reason": "no_executable_api_specs"}
        return report

    if config.run_http_tool:
        http_tool = HttpApiTestTool(
            config.base_url,
            timeout_seconds=config.request_timeout_seconds,
            verify_tls=config.verify_tls,
        )
        for spec in specs:
            report.tool_calls.append(
                ToolInvocation(
                    tool_name="http_api_test",
                    case_id=spec.case_id,
                    arguments={
                        "method": spec.method,
                        "path": spec.path,
                        "expected_status": spec.expected_status,
                    },
                )
            )
            http_result = http_tool.invoke(spec)
            report.http_results.append(http_result)
            collector.collect_http(spec, http_result)

    if config.run_pytest:
        report.tool_calls.append(
            ToolInvocation(
                tool_name="pytest_runner",
                case_id="PYTEST-SUITE",
                arguments={"case_count": len(specs), "base_url": config.base_url},
            )
        )
        report.pytest_result = PytestRunnerTool(config.pytest_timeout_seconds).invoke(
            specs,
            base_url=config.base_url,
            request_timeout_seconds=config.request_timeout_seconds,
            verify_tls=config.verify_tls,
        )
        collector.collect_pytest(report.pytest_result)

    analyses, analysis_warnings = analyse_failures(
        report.http_results,
        llm_settings,
        config,
    )
    report.failure_analysis = analyses
    report.warnings.extend(analysis_warnings)

    total = len(report.http_results)
    passed = sum(1 for item in report.http_results if item.passed)
    failed = total - passed
    report.summary = {
        "status": "completed",
        "total_http_cases": total,
        "passed_http_cases": passed,
        "failed_http_cases": failed,
        "http_pass_rate": round(passed / total, 4) if total else None,
        "pytest_passed": report.pytest_result.passed if report.pytest_result else None,
        "tool_call_count": len(report.tool_calls),
        "failure_analysis_count": len(report.failure_analysis),
    }
    report.diagnostic_evidence.extend(collector.dump())
    report.evidence_collection_overhead_ms = collector.overhead_ms()
    return report
