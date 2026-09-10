"""Transactional persistence for evaluation reports and A/B summaries."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy.orm import Session

from ...config import GenerationConfig, LLMSettings
from ...evaluation.comparison import compare_evaluation_runs
from ...evaluation.engine import default_knowledge_snapshot
from ...evaluation.judge import JUDGE_PROMPT_VERSION, judge_prompt_digest
from ...evaluation.metrics import AGGREGATION_VERSION
from ...evaluation.models import EvaluationRunReport, GoldenDataset
from ...prompts import workflow_prompt_digest
from ..models import EvaluationComparisonORM, EvaluationRunORM
from ..repositories import evaluations


class EvaluationPersistenceService:
    def create_run(
        self,
        session: Session,
        *,
        dataset: GoldenDataset,
        user_id: uuid.UUID | None,
        llm_settings: LLMSettings,
        generation_config: GenerationConfig,
        judge_settings: LLMSettings | None = None,
        run_id: uuid.UUID | None = None,
        knowledge_base_identifier: str | None = None,
        knowledge_base_digest: str | None = None,
        configuration_label: str = "single",
    ) -> EvaluationRunORM:
        judge = judge_settings or llm_settings
        default_identifier, default_digest = default_knowledge_snapshot()
        return evaluations.create_evaluation_run(
            session,
            id=run_id or uuid.uuid4(),
            user_id=user_id,
            status="queued",
            configuration_label=configuration_label[:64] or "single",
            dataset_name=dataset.name,
            dataset_version=dataset.dataset_version,
            dataset_digest=dataset.digest,
            provider=llm_settings.mode,
            model=llm_settings.model,
            temperature=Decimal(str(llm_settings.temperature)),
            seed=llm_settings.seed,
            prompt_version=generation_config.prompt_version,
            prompt_digest=workflow_prompt_digest(generation_config.prompt_version),
            generation_config=generation_config.model_dump(mode="json"),
            judge_config={
                "provider": judge.mode,
                "model": judge.model,
                "temperature": judge.temperature,
                "seed": judge.seed,
                "prompt_version": JUDGE_PROMPT_VERSION,
                "prompt_digest": judge_prompt_digest(),
            },
            knowledge_base_identifier=knowledge_base_identifier or default_identifier,
            knowledge_base_digest=knowledge_base_digest or default_digest,
            aggregation_version=AGGREGATION_VERSION,
        )

    def persist_report(
        self, session: Session, run_id: uuid.UUID, report: EvaluationRunReport
    ) -> EvaluationRunORM:
        run = evaluations.get_evaluation_run_for_update(session, run_id)
        if run is None:
            raise LookupError(f"Evaluation run {run_id} does not exist")
        if run.dataset_version != report.dataset_version or run.dataset_digest != report.dataset_digest:
            raise ValueError("Evaluation report dataset snapshot does not match its run")
        configuration = report.configuration
        expected_metadata = (
            run.provider,
            run.model,
            run.prompt_version,
            run.prompt_digest,
            run.knowledge_base_identifier,
            run.knowledge_base_digest,
        )
        actual_metadata = (
            configuration.provider,
            configuration.model,
            configuration.prompt_version,
            configuration.prompt_digest,
            configuration.knowledge_base_identifier,
            configuration.knowledge_base_digest,
        )
        if expected_metadata != actual_metadata:
            raise ValueError("Evaluation report configuration does not match its run")

        for case in report.cases:
            evaluations.upsert_evaluation_case_result(
                session,
                run_id=run.id,
                dataset_case_id=case.dataset_case_id,
                metric_scores={
                    name: metric.model_dump(mode="json")
                    for name, metric in case.metrics.items()
                },
                overall_score=Decimal(str(case.overall_score)),
                latency_ms=Decimal(str(case.latency_ms)),
                revision_iterations=case.revision_iterations,
                failure_reason=case.failure_reason,
                judge_metadata=case.judge_metadata.model_dump(mode="json"),
                generated_result=case.generated_result,
            )

        run.status = report.status
        run.metric_scores = report.metric_scores
        run.overall_score = Decimal(str(report.overall_score))
        run.revision_iterations = report.revision_iterations
        run.started_at = report.started_at
        run.ended_at = report.ended_at
        run.latency_ms = Decimal(str(report.latency_ms))
        run.failure_reason = report.failure_reason
        session.flush()
        return run

    def create_comparison(
        self,
        session: Session,
        *,
        name: str,
        user_id: uuid.UUID | None,
        dataset: GoldenDataset,
        run_a_id: uuid.UUID,
        run_b_id: uuid.UUID,
    ) -> EvaluationComparisonORM:
        return evaluations.create_evaluation_comparison(
            session,
            user_id=user_id,
            name=name[:255],
            status="queued",
            dataset_version=dataset.dataset_version,
            dataset_digest=dataset.digest,
            run_a_id=run_a_id,
            run_b_id=run_b_id,
        )

    def refresh_comparison(
        self,
        session: Session,
        comparison_id: uuid.UUID,
        run_reports: tuple[EvaluationRunReport, EvaluationRunReport],
    ) -> EvaluationComparisonORM:
        comparison = evaluations.get_evaluation_comparison(session, comparison_id)
        if comparison is None:
            raise LookupError(f"Evaluation comparison {comparison_id} does not exist")
        report = compare_evaluation_runs(*run_reports)
        if (
            comparison.dataset_version != report.dataset_version
            or comparison.dataset_digest != report.dataset_digest
        ):
            raise ValueError("Comparison dataset snapshot does not match its runs")
        comparison.status = "completed"
        comparison.summary = report.model_dump(mode="json")
        comparison.failure_reason = None
        comparison.completed_at = datetime.now(timezone.utc)
        session.flush()
        return comparison

    def refresh_comparisons_for_run(
        self, session: Session, run_id: uuid.UUID
    ) -> list[EvaluationComparisonORM]:
        refreshed: list[EvaluationComparisonORM] = []
        for comparison in evaluations.list_comparisons_for_run(session, run_id):
            run_a = evaluations.get_evaluation_run(session, comparison.run_a_id)
            run_b = evaluations.get_evaluation_run(session, comparison.run_b_id)
            if run_a is None or run_b is None:
                comparison.status = "failed"
                comparison.failure_reason = "A/B run no longer exists"
            elif "failed" in {run_a.status, run_b.status}:
                comparison.status = "failed"
                comparison.failure_reason = "One or both A/B runs failed"
            elif {run_a.status, run_b.status} == {"completed"}:
                metric_names = sorted(set(run_a.metric_scores) | set(run_b.metric_scores))
                comparison.status = "completed"
                comparison.summary = {
                    "dataset_version": comparison.dataset_version,
                    "dataset_digest": comparison.dataset_digest,
                    "metrics": {
                        name: _comparison_values(
                            run_a.metric_scores.get(name, 0), run_b.metric_scores.get(name, 0)
                        )
                        for name in metric_names
                    },
                    "overall": _comparison_values(run_a.overall_score, run_b.overall_score),
                    "latency_ms": _comparison_values(run_a.latency_ms, run_b.latency_ms),
                    "revision_iterations": _comparison_values(
                        run_a.revision_iterations, run_b.revision_iterations
                    ),
                }
                comparison.completed_at = datetime.now(timezone.utc)
                comparison.failure_reason = None
            else:
                comparison.status = "running"
            refreshed.append(comparison)
        session.flush()
        return refreshed


def _comparison_values(value_a, value_b) -> dict[str, float]:
    a = float(value_a or 0)
    b = float(value_b or 0)
    return {
        "configuration_a": a,
        "configuration_b": b,
        "delta": round(b - a, 2),
    }
