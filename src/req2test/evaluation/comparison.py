"""Pure A/B comparison over two persisted-ready evaluation reports."""

from __future__ import annotations

from .models import (
    EVALUATION_METRIC_NAMES,
    EvaluationComparisonReport,
    EvaluationRunReport,
    MetricComparison,
)


def compare_evaluation_runs(
    run_a: EvaluationRunReport, run_b: EvaluationRunReport
) -> EvaluationComparisonReport:
    if (
        run_a.dataset_version != run_b.dataset_version
        or run_a.dataset_digest != run_b.dataset_digest
    ):
        raise ValueError("A/B runs must use the same dataset version and digest")

    return EvaluationComparisonReport(
        dataset_version=run_a.dataset_version,
        dataset_digest=run_a.dataset_digest,
        metrics={
            name: MetricComparison(
                configuration_a=run_a.metric_scores[name],
                configuration_b=run_b.metric_scores[name],
                delta=round(run_b.metric_scores[name] - run_a.metric_scores[name], 2),
            )
            for name in EVALUATION_METRIC_NAMES
        },
        overall=MetricComparison(
            configuration_a=run_a.overall_score,
            configuration_b=run_b.overall_score,
            delta=round(run_b.overall_score - run_a.overall_score, 2),
        ),
        latency_ms=MetricComparison(
            configuration_a=run_a.latency_ms,
            configuration_b=run_b.latency_ms,
            delta=round(run_b.latency_ms - run_a.latency_ms, 2),
        ),
        revision_iterations=MetricComparison(
            configuration_a=float(run_a.revision_iterations),
            configuration_b=float(run_b.revision_iterations),
            delta=float(run_b.revision_iterations - run_a.revision_iterations),
        ),
    )
