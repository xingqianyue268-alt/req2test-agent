"""Evaluation orchestration independent from the workflow's Review Agent."""

from __future__ import annotations

import hashlib
import time
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean

from ..config import GenerationConfig, LLMSettings
from ..graph import run_workflow
from ..models import WorkflowResult
from ..prompts import workflow_prompt_digest
from .judge import JUDGE_PROMPT_VERSION, evaluate_subjective_metrics, judge_prompt_digest
from .metrics import (
    AGGREGATION_VERSION,
    DETERMINISTIC_EVALUATOR_VERSION,
    aggregate_metric_scores,
    evaluate_deterministic_metrics,
)
from .models import (
    EVALUATION_METRIC_NAMES,
    EvaluationCaseReport,
    EvaluationConfigurationMetadata,
    EvaluationMetricName,
    EvaluationMetricResult,
    EvaluationRunReport,
    GoldenDataset,
    GoldenDatasetCase,
    JudgeMetadata,
)
from .safety import safe_failure_reason


def default_knowledge_snapshot() -> tuple[str, str]:
    """Identify the repository knowledge inputs used by the workflow fallback."""

    root = Path(__file__).resolve().parents[3]
    paths = [root / "knowledge" / "testing_rules.md", root / "knowledge" / "historical_cases.jsonl"]
    digest = hashlib.sha256()
    names: list[str] = []
    for path in paths:
        if path.is_file():
            names.append(path.name)
            digest.update(path.name.encode("utf-8"))
            digest.update(b"\0")
            digest.update(path.read_bytes())
            digest.update(b"\0")
    if not names:
        digest.update(b"req2test-empty-knowledge")
    return "repository-knowledge:" + "+".join(names or ["empty"]), digest.hexdigest()


def _failure_metrics(reason: str) -> dict[EvaluationMetricName, EvaluationMetricResult]:
    metrics: dict[EvaluationMetricName, EvaluationMetricResult] = {}
    for name in EVALUATION_METRIC_NAMES:
        deterministic = name in {"requirement_coverage", "case_completeness", "redundancy"}
        metrics[name] = EvaluationMetricResult(
            metric=name,
            score=0.0,
            reason="Evaluation could not score this metric because generation failed.",
            evidence=[{"failure_reason": reason}],
            evaluator="deterministic" if deterministic else "deterministic_fallback",
            evaluator_version=DETERMINISTIC_EVALUATOR_VERSION,
        )
    return metrics


def _public_generated_result(result: WorkflowResult) -> dict:
    """Persist only evaluation artifacts, excluding RAG context and raw model errors."""

    return {
        "requirements": [item.model_dump(mode="json") for item in result.requirements],
        "test_cases": [item.model_dump(mode="json") for item in result.test_cases],
        "review": result.review.model_dump(mode="json"),
        "review_iterations": result.review_iterations,
    }


def _evaluate_case(
    golden: GoldenDatasetCase,
    llm_settings: LLMSettings,
    generation_config: GenerationConfig,
    judge_settings: LLMSettings,
) -> EvaluationCaseReport:
    started = time.perf_counter()
    try:
        result: WorkflowResult = run_workflow(
            golden.requirement_text,
            llm_settings=llm_settings,
            generation_config=generation_config,
        )
        metrics = evaluate_deterministic_metrics(golden, result)
        judge = evaluate_subjective_metrics(golden, result, judge_settings)
        metrics.update(judge.metrics)
        return EvaluationCaseReport(
            dataset_case_id=golden.id,
            metrics=metrics,
            overall_score=aggregate_metric_scores(metrics),
            latency_ms=round((time.perf_counter() - started) * 1000, 2),
            revision_iterations=result.review_iterations,
            judge_metadata=judge.metadata,
            generated_result=_public_generated_result(result),
        )
    except Exception as exc:  # noqa: BLE001 - one bad golden case must not erase a run
        reason = safe_failure_reason(exc, max_length=1000)
        metrics = _failure_metrics(reason)
        return EvaluationCaseReport(
            dataset_case_id=golden.id,
            metrics=metrics,
            overall_score=0.0,
            latency_ms=round((time.perf_counter() - started) * 1000, 2),
            failure_reason=reason,
            judge_metadata=JudgeMetadata(
                provider=judge_settings.mode,
                model=judge_settings.model,
                temperature=judge_settings.temperature,
                prompt_version=JUDGE_PROMPT_VERSION,
                prompt_digest=judge_prompt_digest(),
                fallback_used=True,
                fallback_reason="generation_failed",
            ),
        )


def evaluate_golden_dataset(
    dataset: GoldenDataset,
    *,
    llm_settings: LLMSettings | None = None,
    generation_config: GenerationConfig | None = None,
    judge_settings: LLMSettings | None = None,
    knowledge_base_identifier: str | None = None,
    knowledge_base_digest: str | None = None,
) -> EvaluationRunReport:
    """Evaluate a validated dataset snapshot and return a persistence-ready report."""

    settings = llm_settings or LLMSettings(mode="demo")
    generation = generation_config or GenerationConfig()
    judge = judge_settings or settings
    default_identifier, default_digest = default_knowledge_snapshot()
    kb_identifier = knowledge_base_identifier or default_identifier
    kb_digest = knowledge_base_digest or default_digest
    if len(kb_digest) != 64 or any(char not in "0123456789abcdef" for char in kb_digest):
        raise ValueError("knowledge_base_digest must be a lowercase SHA-256 digest")

    started_at = datetime.now(timezone.utc)
    started = time.perf_counter()
    cases = [
        _evaluate_case(item, settings, generation, judge)
        for item in dataset.cases
    ]
    ended_at = datetime.now(timezone.utc)
    metric_scores = {
        name: round(mean(case.metrics[name].score for case in cases), 2)
        for name in EVALUATION_METRIC_NAMES
    }
    failures = [case for case in cases if case.failure_reason]
    status = "failed" if len(failures) == len(cases) else "completed"
    failure_reason = (
        f"{len(failures)}/{len(cases)} evaluation cases failed"
        if failures
        else None
    )
    return EvaluationRunReport(
        dataset_name=dataset.name,
        dataset_version=dataset.dataset_version,
        dataset_digest=dataset.digest,
        status=status,
        configuration=EvaluationConfigurationMetadata(
            provider=settings.mode,
            model=settings.model,
            temperature=settings.temperature,
            seed=settings.seed,
            prompt_version=generation.prompt_version,
            prompt_digest=workflow_prompt_digest(generation.prompt_version),
            generation_config=generation.model_dump(mode="json"),
            knowledge_base_identifier=kb_identifier,
            knowledge_base_digest=kb_digest,
            aggregation_version=AGGREGATION_VERSION,
        ),
        started_at=started_at,
        ended_at=ended_at,
        latency_ms=round((time.perf_counter() - started) * 1000, 2),
        metric_scores=metric_scores,
        overall_score=round(mean(case.overall_score for case in cases), 2),
        revision_iterations=sum(case.revision_iterations for case in cases),
        failure_reason=failure_reason,
        cases=cases,
    )
