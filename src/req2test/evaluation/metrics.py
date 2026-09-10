"""Deterministic-first quality metrics and versioned score aggregation."""

from __future__ import annotations

import math
import re
from collections.abc import Callable, Mapping

from ..models import RequirementItem, TestCase, WorkflowResult
from .models import (
    EVALUATION_METRIC_NAMES,
    EvaluationMetricName,
    EvaluationMetricResult,
    GoldenDatasetCase,
    GoldenExpectation,
)

DETERMINISTIC_EVALUATOR_VERSION = "deterministic-v1"
AGGREGATION_VERSION = "weighted-v1"

METRIC_WEIGHTS_V1: dict[EvaluationMetricName, float] = {
    "requirement_coverage": 0.25,
    "case_completeness": 0.15,
    "executability": 0.20,
    "expected_result_quality": 0.15,
    "requirement_groundedness": 0.20,
    "redundancy": 0.05,
}

_VAGUE_ACTIONS = (
    "测试一下",
    "验证功能",
    "进行操作",
    "相关操作",
    "适当操作",
    "正常操作",
)
_VAGUE_EXPECTATIONS = (
    "功能正常",
    "结果正确",
    "符合预期",
    "正常即可",
    "显示正常",
)
_OBSERVABLE_TERMS = (
    "展示",
    "显示",
    "返回",
    "提示",
    "保存",
    "更新",
    "拒绝",
    "阻止",
    "生成",
    "进入",
    "不再",
    "状态",
    "数据",
    "文件",
    "响应",
    "页面",
    "会话",
)
_ENDPOINT_PATTERN = re.compile(
    r"\b(?:GET|POST|PUT|PATCH|DELETE|HEAD|OPTIONS)\s+(/[A-Za-z0-9_./?=&%{}:\-]+)",
    flags=re.IGNORECASE,
)


def _normalized_text(value: str) -> str:
    return re.sub(r"[^a-z0-9\u4e00-\u9fff]+", "", value.lower())


def _tokens(value: str) -> set[str]:
    normalized = _normalized_text(value)
    chinese = {
        normalized[index : index + 2]
        for index in range(max(0, len(normalized) - 1))
        if any("\u4e00" <= char <= "\u9fff" for char in normalized[index : index + 2])
    }
    words = set(re.findall(r"[a-z0-9_./?=&%{}:\-]{2,}", value.lower()))
    return chinese | words


def _round_score(value: float) -> float:
    return round(max(0.0, min(100.0, value)), 2)


def _expectation_matches(expectation: GoldenExpectation, text: str) -> tuple[bool, list[str]]:
    normalized = _normalized_text(text)
    matched = [keyword for keyword in expectation.keywords if _normalized_text(keyword) in normalized]
    required = max(1, math.ceil(len(expectation.keywords) * 0.6))
    return len(matched) >= required, matched


def _match_expected_requirement(
    expectation: GoldenExpectation, requirements: list[RequirementItem]
) -> tuple[RequirementItem | None, list[str]]:
    best: tuple[RequirementItem | None, list[str]] = (None, [])
    for requirement in requirements:
        candidate = " ".join(
            [requirement.module, requirement.description, *requirement.acceptance_criteria]
        )
        matches, keywords = _expectation_matches(expectation, candidate)
        if len(keywords) > len(best[1]):
            best = (requirement, keywords)
        if matches:
            return requirement, keywords
    return best


def requirement_coverage(
    golden: GoldenDatasetCase, result: WorkflowResult
) -> EvaluationMetricResult:
    covered_requirement_ids = {case.source_requirement for case in result.test_cases}
    evidence: list[dict[str, object]] = []
    covered = 0
    for expected in golden.expected_requirements:
        matched, keywords = _match_expected_requirement(expected, result.requirements)
        traced = bool(matched and matched.requirement_id in covered_requirement_ids)
        if traced:
            covered += 1
        evidence.append(
            {
                "expectation_id": expected.id,
                "matched_requirement_id": matched.requirement_id if matched else None,
                "matched_keywords": keywords,
                "covered_by_test_case": traced,
            }
        )
    total = len(golden.expected_requirements)
    score = _round_score(100 * covered / total) if total else 100.0
    return EvaluationMetricResult(
        metric="requirement_coverage",
        score=score,
        reason=f"{covered}/{total} golden requirements are matched and traced to test cases.",
        evidence=evidence,
        evaluator="deterministic",
        evaluator_version=DETERMINISTIC_EVALUATOR_VERSION,
    )


def case_completeness(
    _golden: GoldenDatasetCase, result: WorkflowResult
) -> EvaluationMetricResult:
    evidence: list[dict[str, object]] = []
    case_scores: list[float] = []
    for case in result.test_cases:
        orders = [step.order for step in case.steps]
        checks = {
            "case_id": bool(case.case_id.strip()),
            "module": bool(case.module.strip()),
            "title": bool(case.title.strip()),
            "preconditions": bool(case.preconditions),
            "minimum_steps": len(case.steps) >= 2,
            "ordered_steps": orders == sorted(set(orders)) and all(order > 0 for order in orders),
            "step_pairs": bool(case.steps)
            and all(step.action.strip() and step.expected.strip() for step in case.steps),
            "source_requirement": bool(case.source_requirement.strip()),
        }
        case_score = 100 * sum(checks.values()) / len(checks)
        case_scores.append(case_score)
        evidence.append(
            {
                "case_id": case.case_id,
                "score": _round_score(case_score),
                "failed_checks": [name for name, passed in checks.items() if not passed],
            }
        )
    score = _round_score(sum(case_scores) / len(case_scores)) if case_scores else 0.0
    return EvaluationMetricResult(
        metric="case_completeness",
        score=score,
        reason=f"Structural completeness was checked for {len(case_scores)} test cases.",
        evidence=evidence,
        evaluator="deterministic",
        evaluator_version=DETERMINISTIC_EVALUATOR_VERSION,
    )


def _case_similarity(left: TestCase, right: TestCase) -> float:
    left_text = " ".join(
        [left.title, *[step.action for step in left.steps], *[step.expected for step in left.steps]]
    )
    right_text = " ".join(
        [right.title, *[step.action for step in right.steps], *[step.expected for step in right.steps]]
    )
    left_tokens, right_tokens = _tokens(left_text), _tokens(right_text)
    union = left_tokens | right_tokens
    return len(left_tokens & right_tokens) / len(union) if union else 0.0


def redundancy(_golden: GoldenDatasetCase, result: WorkflowResult) -> EvaluationMetricResult:
    redundant_case_ids: set[str] = set()
    evidence: list[dict[str, object]] = []
    for left_index, left in enumerate(result.test_cases):
        for right in result.test_cases[left_index + 1 :]:
            exact_title = _normalized_text(left.title) == _normalized_text(right.title)
            similarity = _case_similarity(left, right)
            same_variant = (
                left.source_requirement == right.source_requirement
                and left.test_type == right.test_type
            )
            if exact_title or (same_variant and similarity >= 0.85):
                redundant_case_ids.add(right.case_id)
                evidence.append(
                    {
                        "left_case_id": left.case_id,
                        "right_case_id": right.case_id,
                        "similarity": round(similarity, 4),
                        "exact_title": exact_title,
                    }
                )
    total = len(result.test_cases)
    score = _round_score(100 * (1 - len(redundant_case_ids) / total)) if total else 0.0
    return EvaluationMetricResult(
        metric="redundancy",
        score=score,
        reason=(
            f"Detected {len(redundant_case_ids)} redundant cases among {total} generated cases."
        ),
        evidence=evidence,
        evaluator="deterministic",
        evaluator_version=DETERMINISTIC_EVALUATOR_VERSION,
    )


def executability_fallback(
    _golden: GoldenDatasetCase, result: WorkflowResult
) -> EvaluationMetricResult:
    evidence: list[dict[str, object]] = []
    checks: list[bool] = []
    for case in result.test_cases:
        failed_steps: list[int] = []
        for step in case.steps:
            action = step.action.strip()
            passed = len(action) >= 4 and not any(term in action for term in _VAGUE_ACTIONS)
            checks.append(passed)
            if not passed:
                failed_steps.append(step.order)
        checks.append(bool(case.preconditions))
        if failed_steps or not case.preconditions:
            evidence.append(
                {
                    "case_id": case.case_id,
                    "vague_or_empty_action_steps": failed_steps,
                    "has_preconditions": bool(case.preconditions),
                }
            )
    score = _round_score(100 * sum(checks) / len(checks)) if checks else 0.0
    return EvaluationMetricResult(
        metric="executability",
        score=score,
        reason="Fallback checks action specificity and the presence of preconditions.",
        evidence=evidence,
        evaluator="deterministic_fallback",
        evaluator_version=DETERMINISTIC_EVALUATOR_VERSION,
    )


def expected_result_quality_fallback(
    _golden: GoldenDatasetCase, result: WorkflowResult
) -> EvaluationMetricResult:
    evidence: list[dict[str, object]] = []
    checks: list[bool] = []
    for case in result.test_cases:
        weak_steps: list[int] = []
        for step in case.steps:
            expected = step.expected.strip()
            passed = (
                len(expected) >= 6
                and not any(term in expected for term in _VAGUE_EXPECTATIONS)
                and any(term in expected for term in _OBSERVABLE_TERMS)
            )
            checks.append(passed)
            if not passed:
                weak_steps.append(step.order)
        if weak_steps:
            evidence.append({"case_id": case.case_id, "weak_expected_steps": weak_steps})
    score = _round_score(100 * sum(checks) / len(checks)) if checks else 0.0
    return EvaluationMetricResult(
        metric="expected_result_quality",
        score=score,
        reason="Fallback checks that every expected result is specific and observable.",
        evidence=evidence,
        evaluator="deterministic_fallback",
        evaluator_version=DETERMINISTIC_EVALUATOR_VERSION,
    )


def requirement_groundedness_fallback(
    golden: GoldenDatasetCase, result: WorkflowResult
) -> EvaluationMetricResult:
    requirement_by_id = {item.requirement_id: item for item in result.requirements}
    allowed_endpoints = {match.upper() for match in _ENDPOINT_PATTERN.findall(golden.requirement_text)}
    evidence: list[dict[str, object]] = []
    scores: list[float] = []

    expectations = [*golden.expected_requirements, *golden.expected_constraints]
    for case in result.test_cases:
        source = requirement_by_id.get(case.source_requirement)
        case_text = " ".join(
            [
                case.title,
                case.rationale,
                *case.preconditions,
                *[step.action for step in case.steps],
                *[step.expected for step in case.steps],
            ]
        )
        matching_expectations = [
            expectation
            for expectation in expectations
            if source
            and _expectation_matches(
                expectation,
                " ".join([source.description, *source.acceptance_criteria]),
            )[0]
        ]
        keyword_total = sum(len(item.keywords) for item in matching_expectations)
        keyword_hits = sum(
            1
            for item in matching_expectations
            for keyword in item.keywords
            if _normalized_text(keyword) in _normalized_text(case_text)
        )
        anchor_score = keyword_hits / keyword_total if keyword_total else (1.0 if source else 0.0)
        generated_endpoints = {
            endpoint.upper() for endpoint in _ENDPOINT_PATTERN.findall(case_text)
        }
        endpoint_safe = not generated_endpoints or generated_endpoints <= allowed_endpoints
        case_score = 50 * bool(source) + 30 * anchor_score + 20 * endpoint_safe
        scores.append(case_score)
        if not source or anchor_score < 0.6 or not endpoint_safe:
            evidence.append(
                {
                    "case_id": case.case_id,
                    "source_requirement_found": bool(source),
                    "keyword_anchor_rate": round(anchor_score, 4),
                    "unapproved_endpoints": sorted(generated_endpoints - allowed_endpoints),
                }
            )

    score = _round_score(sum(scores) / len(scores)) if scores else 0.0
    return EvaluationMetricResult(
        metric="requirement_groundedness",
        score=score,
        reason="Fallback checks traceability, golden keyword anchors, and endpoint boundaries.",
        evidence=evidence,
        evaluator="deterministic_fallback",
        evaluator_version=DETERMINISTIC_EVALUATOR_VERSION,
    )


MetricEvaluator = Callable[[GoldenDatasetCase, WorkflowResult], EvaluationMetricResult]

_DETERMINISTIC_METRICS: tuple[MetricEvaluator, ...] = (
    requirement_coverage,
    case_completeness,
    redundancy,
)
_DETERMINISTIC_FALLBACK_METRICS: tuple[MetricEvaluator, ...] = (
    executability_fallback,
    expected_result_quality_fallback,
    requirement_groundedness_fallback,
)


def evaluate_deterministic_metrics(
    golden: GoldenDatasetCase, result: WorkflowResult
) -> dict[EvaluationMetricName, EvaluationMetricResult]:
    results = [evaluator(golden, result) for evaluator in _DETERMINISTIC_METRICS]
    return {metric.metric: metric for metric in results}


def evaluate_deterministic_fallback_metrics(
    golden: GoldenDatasetCase, result: WorkflowResult
) -> dict[EvaluationMetricName, EvaluationMetricResult]:
    results = [evaluator(golden, result) for evaluator in _DETERMINISTIC_FALLBACK_METRICS]
    return {metric.metric: metric for metric in results}


def aggregate_metric_scores(
    metrics: Mapping[str, EvaluationMetricResult],
    weights: Mapping[EvaluationMetricName, float] | None = None,
) -> float:
    active_weights = dict(weights or METRIC_WEIGHTS_V1)
    missing = set(EVALUATION_METRIC_NAMES) - set(metrics)
    extra = set(metrics) - set(EVALUATION_METRIC_NAMES)
    if missing or extra:
        raise ValueError(
            f"Metric set must be complete; missing={sorted(missing)}, extra={sorted(extra)}"
        )
    if set(active_weights) != set(EVALUATION_METRIC_NAMES):
        raise ValueError("Metric weights must contain every evaluation metric exactly once")
    total_weight = sum(active_weights.values())
    if not math.isclose(total_weight, 1.0, abs_tol=1e-9):
        raise ValueError(f"Metric weights must sum to 1.0, found {total_weight}")
    return _round_score(
        sum(metrics[name].score * active_weights[name] for name in EVALUATION_METRIC_NAMES)
    )
