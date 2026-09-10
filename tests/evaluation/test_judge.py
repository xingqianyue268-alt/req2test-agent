from __future__ import annotations

from req2test.config import LLMSettings
from req2test.evaluation.judge import evaluate_subjective_metrics
from req2test.evaluation.models import GoldenDatasetCase
from req2test.models import RequirementItem, ReviewReport, WorkflowResult
from req2test.models import TestCase as CaseModel
from req2test.models import TestStep as StepModel


def _golden():
    return GoldenDatasetCase.model_validate(
        {
            "id": "judge-case",
            "requirement_text": "用户可以使用账号和密码登录。",
            "expected_requirements": [
                {
                    "id": "REQ-G-1",
                    "text": "账号密码登录",
                    "keywords": ["账号", "密码", "登录"],
                }
            ],
            "expected_constraints": [],
            "tags": ["demo"],
            "dataset_version": "v1",
        }
    )


def _result():
    return WorkflowResult(
        requirements=[
            RequirementItem(
                requirement_id="REQ-001",
                module="登录",
                description="用户可以使用账号和密码登录",
            )
        ],
        test_cases=[
            CaseModel(
                case_id="TC-001",
                module="登录",
                title="验证账号密码登录",
                preconditions=["已准备测试账号"],
                steps=[
                    StepModel(
                        order=1,
                        action="输入有效账号和密码",
                        expected="页面展示登录提交入口",
                    ),
                    StepModel(
                        order=2,
                        action="点击登录",
                        expected="系统进入用户首页并创建会话",
                    ),
                ],
                source_requirement="REQ-001",
                rationale="覆盖登录需求",
            )
        ],
        review=ReviewReport(score=100, coverage_rate=1.0),
    )


def test_demo_judge_is_fully_offline_and_uses_deterministic_fallback(monkeypatch):
    def forbidden_model(_settings):
        raise AssertionError("demo mode must not build an LLM client")

    monkeypatch.setattr("req2test.evaluation.judge.build_chat_model", forbidden_model)
    outcome = evaluate_subjective_metrics(
        _golden(), _result(), LLMSettings(mode="demo")
    )

    assert outcome.metadata.fallback_used is True
    assert outcome.metadata.fallback_reason == "offline_demo"
    assert set(outcome.metrics) == {
        "executability",
        "expected_result_quality",
        "requirement_groundedness",
    }
    assert {item.evaluator for item in outcome.metrics.values()} == {
        "deterministic_fallback"
    }


def test_online_judge_validates_structured_json_and_never_sends_api_key(monkeypatch):
    captured = {}

    monkeypatch.setattr("req2test.evaluation.judge.build_chat_model", lambda _settings: object())

    def fake_invoke(_model, system_prompt, user_prompt):
        captured["system"] = system_prompt
        captured["user"] = user_prompt
        return {
            "metrics": [
                {
                    "metric": "executability",
                    "score": 91,
                    "reason": "步骤清晰",
                    "evidence": [{"case_id": "TC-001", "finding": "可直接执行"}],
                },
                {
                    "metric": "expected_result_quality",
                    "score": 88,
                    "reason": "结果可观察",
                    "evidence": [],
                },
                {
                    "metric": "requirement_groundedness",
                    "score": 94,
                    "reason": "忠于需求",
                    "evidence": [],
                },
            ]
        }

    monkeypatch.setattr("req2test.evaluation.judge.invoke_json", fake_invoke)
    outcome = evaluate_subjective_metrics(
        _golden(),
        _result(),
        LLMSettings(
            mode="openai_compatible",
            model="judge-model",
            api_key="do-not-send-this-key",
        ),
    )

    assert outcome.metadata.fallback_used is False
    assert outcome.metrics["executability"].evaluator == "llm_judge"
    assert outcome.metrics["executability"].score == 91
    assert "do-not-send-this-key" not in captured["system"]
    assert "do-not-send-this-key" not in captured["user"]
    assert "api_key" not in outcome.model_dump_json()


def test_invalid_judge_output_falls_back_and_redacts_failure(monkeypatch):
    monkeypatch.setattr("req2test.evaluation.judge.build_chat_model", lambda _settings: object())

    def invalid_output(*_args):
        raise RuntimeError("authorization=super-secret-token judge failed")

    monkeypatch.setattr("req2test.evaluation.judge.invoke_json", invalid_output)
    outcome = evaluate_subjective_metrics(
        _golden(),
        _result(),
        LLMSettings(mode="openai_compatible", model="broken-judge", api_key="hidden"),
    )

    assert outcome.metadata.fallback_used is True
    assert "super-secret-token" not in outcome.metadata.fallback_reason
    assert "authorization=***" in outcome.metadata.fallback_reason
    assert {item.evaluator for item in outcome.metrics.values()} == {
        "deterministic_fallback"
    }


def test_incomplete_or_extra_judge_json_uses_fallback(monkeypatch):
    monkeypatch.setattr("req2test.evaluation.judge.build_chat_model", lambda _settings: object())
    monkeypatch.setattr(
        "req2test.evaluation.judge.invoke_json",
        lambda *_args: {
            "metrics": [
                {
                    "metric": "executability",
                    "score": 90,
                    "reason": "ok",
                    "evidence": [],
                    "unexpected": True,
                }
            ]
        },
    )

    outcome = evaluate_subjective_metrics(
        _golden(), _result(), LLMSettings(mode="openai_compatible", model="judge")
    )

    assert outcome.metadata.fallback_used is True
