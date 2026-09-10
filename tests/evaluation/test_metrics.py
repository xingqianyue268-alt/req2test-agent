from __future__ import annotations

import pytest

from req2test.evaluation.metrics import (
    aggregate_metric_scores,
    evaluate_deterministic_fallback_metrics,
    evaluate_deterministic_metrics,
)
from req2test.evaluation.models import EvaluationMetricResult, GoldenDatasetCase
from req2test.models import (
    RequirementItem,
    ReviewReport,
    WorkflowResult,
)
from req2test.models import (
    TestCase as CaseModel,
)
from req2test.models import (
    TestStep as StepModel,
)


def _golden():
    return GoldenDatasetCase.model_validate(
        {
            "id": "login",
            "requirement_text": "# 登录\n用户可以使用账号和密码登录。",
            "expected_requirements": [
                {
                    "id": "G-1",
                    "text": "账号密码登录",
                    "keywords": ["账号", "密码", "登录"],
                }
            ],
            "expected_constraints": [],
            "tags": ["demo"],
            "dataset_version": "v1",
        }
    )


def _case(case_id="TC-001", title="验证账号密码登录"):
    return CaseModel(
        case_id=case_id,
        module="登录",
        title=title,
        preconditions=["测试环境可访问", "已准备有效账号"],
        steps=[
            StepModel(order=1, action="输入有效账号和密码", expected="页面展示登录提交入口"),
            StepModel(order=2, action="点击登录按钮", expected="系统进入用户首页并创建会话"),
        ],
        source_requirement="REQ-001",
        rationale="覆盖账号密码登录需求",
    )


def _result(cases=None):
    return WorkflowResult(
        requirements=[
            RequirementItem(
                requirement_id="REQ-001",
                module="登录",
                description="用户可以使用账号和密码登录",
            )
        ],
        test_cases=cases if cases is not None else [_case()],
        review=ReviewReport(score=100, coverage_rate=1.0),
    )


def test_deterministic_first_metrics_are_normalized_and_do_not_use_judge():
    metrics = evaluate_deterministic_metrics(_golden(), _result())

    assert set(metrics) == {"requirement_coverage", "case_completeness", "redundancy"}
    assert {item.evaluator for item in metrics.values()} == {"deterministic"}
    assert {item.score for item in metrics.values()} == {100.0}
    assert all(item.reason and isinstance(item.evidence, list) for item in metrics.values())


def test_redundancy_detects_duplicate_cases_and_completeness_detects_missing_fields():
    duplicate = _case("TC-002")
    incomplete = _case("TC-003", "")
    incomplete.preconditions = []
    incomplete.steps = [StepModel(order=2, action="", expected="")]

    metrics = evaluate_deterministic_metrics(
        _golden(), _result([_case(), duplicate, incomplete])
    )

    assert metrics["redundancy"].score < 100
    assert metrics["redundancy"].evidence
    assert metrics["case_completeness"].score < 100
    assert "title" in metrics["case_completeness"].evidence[-1]["failed_checks"]


def test_subjective_metric_fallbacks_return_the_same_strict_contract():
    metrics = evaluate_deterministic_fallback_metrics(_golden(), _result())

    assert set(metrics) == {
        "executability",
        "expected_result_quality",
        "requirement_groundedness",
    }
    assert {item.evaluator for item in metrics.values()} == {"deterministic_fallback"}
    assert all(0 <= item.score <= 100 for item in metrics.values())


def test_weighted_aggregation_requires_all_six_metrics():
    metrics = {
        name: EvaluationMetricResult(
            metric=name,
            score=score,
            reason="test",
            evaluator="deterministic",
            evaluator_version="test-v1",
        )
        for name, score in {
            "requirement_coverage": 100,
            "case_completeness": 80,
            "executability": 70,
            "expected_result_quality": 60,
            "requirement_groundedness": 90,
            "redundancy": 100,
        }.items()
    }

    assert aggregate_metric_scores(metrics) == 83.0
    metrics.pop("redundancy")
    with pytest.raises(ValueError, match="complete"):
        aggregate_metric_scores(metrics)
