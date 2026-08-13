"""Deterministic, evidence-first root-cause classification.

The classifier never invents facts and does not require an LLM. Every diagnosis
contains references to the structured evidence that triggered the rule.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field

from .evidence import EvidenceSeverity, EvidenceType, FailureEvidence


class RootCauseCategory(StrEnum):
    CONTRACT_MISMATCH = "contract_mismatch"
    UPSTREAM_API_ERROR = "upstream_api_error"
    ASSERTION_FAILURE = "assertion_failure"
    RAG_RETRIEVAL_ISSUE = "rag_retrieval_issue"
    LLM_OUTPUT_ISSUE = "llm_output_issue"
    ENVIRONMENT_ERROR = "environment_error"
    TIMEOUT = "timeout"
    AUTHENTICATION_ERROR = "authentication_error"
    TEST_DATA_ISSUE = "test_data_issue"
    INTERNAL_ERROR = "internal_error"
    UNKNOWN = "unknown"


class DiagnosisConfidence(StrEnum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class FailureDiagnosis(BaseModel):
    case_id: str | None = None
    category: RootCauseCategory
    confidence: DiagnosisConfidence
    probable_cause: str
    evidence_refs: list[str] = Field(default_factory=list)
    evidence_summary: list[str] = Field(default_factory=list)
    suggestion: str
    diagnosis_source: str = "rule"


class FailureDiagnosisSummary(BaseModel):
    failure_count: int = 0
    category_distribution: dict[str, int] = Field(default_factory=dict)
    primary_failure_category: str | None = None


class FailureAnalysisV2(BaseModel):
    trace_id: str
    summary: FailureDiagnosisSummary
    diagnoses: list[FailureDiagnosis] = Field(default_factory=list)


_SUGGESTIONS = {
    RootCauseCategory.CONTRACT_MISMATCH: (
        "检查接口契约中的必填字段、字段类型、query 与 Content-Type；"
        "对比已脱敏的实际请求和 OpenAPI/需求约束。"
    ),
    RootCauseCategory.UPSTREAM_API_ERROR: (
        "按证据中的请求时间和路径检查目标服务及其下游依赖日志，确认 5xx 的服务端原因。"
    ),
    RootCauseCategory.ASSERTION_FAILURE: (
        "对比实际响应与需求验收标准，确认产品行为缺陷或测试期望是否需要更新。"
    ),
    RootCauseCategory.RAG_RETRIEVAL_ISSUE: (
        "检查知识库索引状态、检索 query、top_k 和测试规则覆盖；补充相关文档后重新检索。"
    ),
    RootCauseCategory.LLM_OUTPUT_ISSUE: (
        "检查结构化输出约束、字段 schema 和模型响应解析；保留确定性回退路径。"
    ),
    RootCauseCategory.ENVIRONMENT_ERROR: (
        "根据失败依赖的真实检查结果恢复 PostgreSQL、Redis、RabbitMQ、Worker 或 Chroma，再重试任务。"
    ),
    RootCauseCategory.TIMEOUT: (
        "检查目标服务可用性、网络链路、下游耗时及当前 timeout 配置，避免盲目提高超时上限。"
    ),
    RootCauseCategory.AUTHENTICATION_ERROR: (
        "检查测试凭证是否存在、有效且具备所需权限范围；不要在诊断或日志中输出真实 token。"
    ),
    RootCauseCategory.TEST_DATA_ISSUE: (
        "核对测试资源 ID、前置数据和环境数据状态，并建立可重复的测试数据准备步骤。"
    ),
    RootCauseCategory.INTERNAL_ERROR: (
        "根据 Worker 异常类型和失败阶段检查平台内部代码路径，并使用 trace_id 关联服务日志。"
    ),
    RootCauseCategory.UNKNOWN: (
        "当前证据不足；补充可复现步骤、相关阶段证据和安全裁剪后的错误上下文后重新诊断。"
    ),
}

_PRIORITY = {
    RootCauseCategory.ENVIRONMENT_ERROR: 100,
    RootCauseCategory.INTERNAL_ERROR: 95,
    RootCauseCategory.TIMEOUT: 90,
    RootCauseCategory.AUTHENTICATION_ERROR: 85,
    RootCauseCategory.CONTRACT_MISMATCH: 80,
    RootCauseCategory.UPSTREAM_API_ERROR: 75,
    RootCauseCategory.LLM_OUTPUT_ISSUE: 70,
    RootCauseCategory.RAG_RETRIEVAL_ISSUE: 65,
    RootCauseCategory.ASSERTION_FAILURE: 60,
    RootCauseCategory.TEST_DATA_ISSUE: 55,
    RootCauseCategory.UNKNOWN: 0,
}


def _summary(items: list[FailureEvidence]) -> tuple[list[str], list[str]]:
    refs = [item.evidence_id for item in items]
    messages = [item.summary for item in items]
    return refs, messages


def _diagnosis(
    items: list[FailureEvidence],
    category: RootCauseCategory,
    confidence: DiagnosisConfidence,
    cause: str,
    *,
    case_id: str | None = None,
) -> FailureDiagnosis:
    refs, messages = _summary(items)
    return FailureDiagnosis(
        case_id=case_id,
        category=category,
        confidence=confidence,
        probable_cause=cause,
        evidence_refs=refs,
        evidence_summary=messages,
        suggestion=_SUGGESTIONS[category],
    )


def _http_status(item: FailureEvidence) -> int | None:
    value = item.details.get("actual_status")
    return int(value) if isinstance(value, int) or str(value).isdigit() else None


def _classify_group(
    items: list[FailureEvidence], *, case_id: str | None
) -> FailureDiagnosis | None:
    errors = [
        item
        for item in items
        if item.severity in {EvidenceSeverity.ERROR, EvidenceSeverity.CRITICAL}
    ]
    has_empty_rag = any(
        item.evidence_type == EvidenceType.RAG_RETRIEVAL
        and item.details.get("returned_count") == 0
        for item in items
    )
    if not errors and not has_empty_rag:
        return None

    infrastructure = [item for item in errors if item.evidence_type == EvidenceType.INFRASTRUCTURE]
    if infrastructure:
        return _diagnosis(
            infrastructure,
            RootCauseCategory.ENVIRONMENT_ERROR,
            DiagnosisConfidence.HIGH,
            "一个或多个平台依赖的真实检查结果为不可用，阻断了测试执行链路。",
            case_id=case_id,
        )

    worker = [item for item in errors if item.evidence_type == EvidenceType.WORKER_EXCEPTION]
    if worker:
        text = " ".join(str(item.details) for item in worker).lower()
        if any(token in text for token in ("redis", "postgres", "database", "rabbit", "broker", "chroma")):
            return _diagnosis(
                worker,
                RootCauseCategory.ENVIRONMENT_ERROR,
                DiagnosisConfidence.MEDIUM,
                "Worker 异常明确关联平台基础设施依赖。",
                case_id=case_id,
            )
        return _diagnosis(
            worker,
            RootCauseCategory.INTERNAL_ERROR,
            DiagnosisConfidence.MEDIUM,
            "平台 Worker 在执行阶段抛出内部异常。",
            case_id=case_id,
        )

    timeouts = [item for item in errors if item.evidence_type == EvidenceType.TIMEOUT]
    if timeouts:
        return _diagnosis(
            timeouts,
            RootCauseCategory.TIMEOUT,
            DiagnosisConfidence.HIGH,
            "目标接口没有在配置的超时时间内完成响应。",
            case_id=case_id,
        )

    responses = [item for item in items if item.evidence_type == EvidenceType.HTTP_RESPONSE]
    auth = [item for item in responses if _http_status(item) in {401, 403}]
    if auth:
        return _diagnosis(
            auth,
            RootCauseCategory.AUTHENTICATION_ERROR,
            DiagnosisConfidence.HIGH,
            "目标接口明确返回认证或授权拒绝。",
            case_id=case_id,
        )

    validation = [item for item in errors if item.evidence_type == EvidenceType.VALIDATION]
    validation_422 = [
        item
        for item in validation
        if item.details.get("actual_status") == 422
        and item.details.get("suspected_contract_issue") is True
        and bool(item.details.get("validation_error"))
    ]
    if validation_422:
        return _diagnosis(
            validation_422,
            RootCauseCategory.CONTRACT_MISMATCH,
            DiagnosisConfidence.HIGH,
            "请求已到达目标接口，但服务端返回了可观察的参数或请求体校验错误。",
            case_id=case_id,
        )

    upstream = [item for item in responses if (_http_status(item) or 0) >= 500]
    if upstream:
        return _diagnosis(
            upstream,
            RootCauseCategory.UPSTREAM_API_ERROR,
            DiagnosisConfidence.HIGH,
            "目标服务已响应，但返回了 5xx 服务端错误。",
            case_id=case_id,
        )

    llm = [
        item
        for item in errors
        if item.evidence_type == EvidenceType.LLM_GENERATION
        and item.details.get("structured_output_parse_success") is False
    ]
    if llm:
        return _diagnosis(
            llm,
            RootCauseCategory.LLM_OUTPUT_ISSUE,
            DiagnosisConfidence.HIGH,
            "模型输出未通过结构化解析或 schema 校验。",
            case_id=case_id,
        )

    rag = [
        item
        for item in items
        if item.evidence_type == EvidenceType.RAG_RETRIEVAL
        and item.details.get("returned_count") == 0
    ]
    if rag:
        return _diagnosis(
            rag,
            RootCauseCategory.RAG_RETRIEVAL_ISSUE,
            DiagnosisConfidence.MEDIUM,
            "依赖测试知识的检索阶段没有返回任何上下文。",
            case_id=case_id,
        )

    assertions = [
        item
        for item in errors
        if item.evidence_type in {EvidenceType.ASSERTION, EvidenceType.PYTEST}
    ]
    if assertions:
        return _diagnosis(
            assertions,
            RootCauseCategory.ASSERTION_FAILURE,
            DiagnosisConfidence.MEDIUM,
            "接口执行完成，但实际结果没有满足一个或多个测试断言。",
            case_id=case_id,
        )

    return _diagnosis(
        errors,
        RootCauseCategory.UNKNOWN,
        DiagnosisConfidence.LOW,
        "存在失败证据，但当前规则无法从这些事实中确定稳定根因。",
        case_id=case_id,
    )


def classify_failures(
    evidence: list[FailureEvidence | dict[str, Any]], *, trace_id: str
) -> FailureAnalysisV2:
    items = [
        item if isinstance(item, FailureEvidence) else FailureEvidence.model_validate(item)
        for item in evidence
    ]
    grouped: dict[str | None, list[FailureEvidence]] = defaultdict(list)
    for item in items:
        grouped[item.case_id].append(item)

    diagnoses = []
    for case_id, group in sorted(grouped.items(), key=lambda pair: pair[0] or ""):
        diagnosis = _classify_group(group, case_id=case_id)
        if diagnosis is not None:
            diagnoses.append(diagnosis)

    counts = Counter(str(item.category) for item in diagnoses)
    primary = None
    if counts:
        primary = max(
            counts,
            key=lambda category: (
                _PRIORITY[RootCauseCategory(category)], counts[category], category
            ),
        )
    return FailureAnalysisV2(
        trace_id=trace_id,
        summary=FailureDiagnosisSummary(
            failure_count=len(diagnoses),
            category_distribution=dict(sorted(counts.items())),
            primary_failure_category=primary,
        ),
        diagnoses=diagnoses,
    )
