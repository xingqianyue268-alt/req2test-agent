from __future__ import annotations

from req2test.config import GenerationConfig, LLMSettings
from req2test.evaluation.dataset import load_golden_dataset
from req2test.evaluation.engine import evaluate_golden_dataset
from req2test.prompts import workflow_prompt_digest


def test_demo_engine_is_offline_complete_and_persistence_ready(monkeypatch):
    dataset = load_golden_dataset("evals/golden_demo.jsonl")

    def no_model(_settings):
        raise AssertionError("demo evaluation must not build a model")

    monkeypatch.setattr("req2test.evaluation.judge.build_chat_model", no_model)
    report = evaluate_golden_dataset(
        dataset,
        llm_settings=LLMSettings(mode="demo", model="demo-generator", seed=7),
        generation_config=GenerationConfig(
            include_positive=True,
            include_negative=True,
            include_edge=False,
            max_cases=30,
            prompt_version="workflow-v1",
        ),
    )

    assert report.status == "completed"
    assert report.dataset_version == "golden-demo-v1"
    assert report.dataset_digest == dataset.digest
    assert len(report.cases) == len(dataset.cases)
    assert set(report.metric_scores) == {
        "requirement_coverage",
        "case_completeness",
        "executability",
        "expected_result_quality",
        "requirement_groundedness",
        "redundancy",
    }
    assert 0 <= report.overall_score <= 100
    assert report.configuration.seed == 7
    assert report.configuration.prompt_digest == workflow_prompt_digest("workflow-v1")
    assert len(report.configuration.knowledge_base_digest) == 64
    assert "api_key" not in report.model_dump_json()
    assert "retrieved_context" not in report.cases[0].generated_result
    assert "errors" not in report.cases[0].generated_result


def test_prompt_versions_have_distinct_stable_digests_and_default_is_compatible():
    assert GenerationConfig().prompt_version == "workflow-v1"
    assert workflow_prompt_digest("workflow-v1") == workflow_prompt_digest("workflow-v1")
    assert workflow_prompt_digest("workflow-v1") != workflow_prompt_digest(
        "workflow-grounded-v2"
    )


def test_engine_records_case_failure_without_losing_dataset_run(monkeypatch):
    dataset = load_golden_dataset("evals/golden_demo.jsonl")
    calls = 0

    def partly_broken(*_args, **_kwargs):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise RuntimeError("generation unavailable")
        from req2test.graph import run_workflow as real_run_workflow

        return real_run_workflow(*_args, **_kwargs)

    monkeypatch.setattr("req2test.evaluation.engine.run_workflow", partly_broken)
    report = evaluate_golden_dataset(dataset)

    assert report.status == "completed"
    assert report.failure_reason == f"1/{len(dataset.cases)} evaluation cases failed"
    assert report.cases[0].overall_score == 0
    assert report.cases[0].failure_reason == "generation unavailable"
