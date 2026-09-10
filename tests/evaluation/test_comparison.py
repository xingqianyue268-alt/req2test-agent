from __future__ import annotations

from copy import deepcopy

import pytest

from req2test.evaluation.comparison import compare_evaluation_runs
from req2test.evaluation.dataset import load_golden_dataset
from req2test.evaluation.engine import evaluate_golden_dataset


def test_ab_comparison_reports_each_metric_overall_latency_and_revisions():
    dataset = load_golden_dataset("evals/golden_demo.jsonl")
    run_a = evaluate_golden_dataset(dataset)
    run_b = deepcopy(run_a)
    run_b.metric_scores["executability"] = 95.0
    run_b.overall_score = round(run_a.overall_score - 1.0, 2)
    run_b.latency_ms = run_a.latency_ms + 25
    run_b.revision_iterations = run_a.revision_iterations + 2

    comparison = compare_evaluation_runs(run_a, run_b)

    assert comparison.metrics["executability"].delta == (
        95.0 - run_a.metric_scores["executability"]
    )
    assert comparison.overall.delta == -1.0
    assert comparison.latency_ms.delta == 25.0
    assert comparison.revision_iterations.delta == 2.0


def test_ab_comparison_rejects_different_dataset_snapshot():
    dataset = load_golden_dataset("evals/golden_demo.jsonl")
    run_a = evaluate_golden_dataset(dataset)
    run_b = deepcopy(run_a)
    run_b.dataset_digest = "f" * 64

    with pytest.raises(ValueError, match="same dataset"):
        compare_evaluation_runs(run_a, run_b)
