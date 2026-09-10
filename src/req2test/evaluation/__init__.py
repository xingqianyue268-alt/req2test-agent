"""Offline and regression evaluation contracts for Req2Test."""

from .dataset import DatasetLoadError, discover_golden_datasets, load_golden_dataset
from .engine import default_knowledge_snapshot, evaluate_golden_dataset
from .judge import JUDGE_PROMPT_VERSION, evaluate_subjective_metrics, judge_prompt_digest
from .metrics import (
    METRIC_WEIGHTS_V1,
    aggregate_metric_scores,
    evaluate_deterministic_fallback_metrics,
    evaluate_deterministic_metrics,
)
from .models import (
    EVALUATION_METRIC_NAMES,
    EvaluationMetricResult,
    GoldenDataset,
    GoldenDatasetCase,
    GoldenExpectation,
    JudgeMetadata,
    JudgeOutcome,
)

__all__ = [
    "EVALUATION_METRIC_NAMES",
    "JUDGE_PROMPT_VERSION",
    "METRIC_WEIGHTS_V1",
    "DatasetLoadError",
    "EvaluationMetricResult",
    "GoldenDataset",
    "GoldenDatasetCase",
    "GoldenExpectation",
    "JudgeMetadata",
    "JudgeOutcome",
    "aggregate_metric_scores",
    "default_knowledge_snapshot",
    "discover_golden_datasets",
    "evaluate_deterministic_fallback_metrics",
    "evaluate_deterministic_metrics",
    "evaluate_golden_dataset",
    "evaluate_subjective_metrics",
    "judge_prompt_digest",
    "load_golden_dataset",
]
