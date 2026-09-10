"""Repository functions for Evaluation Center persistence."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session, selectinload

from ..models import EvaluationCaseResultORM, EvaluationComparisonORM, EvaluationRunORM


def create_evaluation_run(session: Session, **values: Any) -> EvaluationRunORM:
    run = EvaluationRunORM(**values)
    session.add(run)
    session.flush()
    return run


def get_evaluation_run(
    session: Session, run_id: uuid.UUID, *, include_cases: bool = False
) -> EvaluationRunORM | None:
    statement = select(EvaluationRunORM).where(EvaluationRunORM.id == run_id)
    if include_cases:
        statement = statement.options(selectinload(EvaluationRunORM.case_results))
    return session.scalar(statement)


def get_evaluation_run_for_update(
    session: Session, run_id: uuid.UUID
) -> EvaluationRunORM | None:
    return session.scalar(
        select(EvaluationRunORM).where(EvaluationRunORM.id == run_id).with_for_update()
    )


def list_evaluation_runs(
    session: Session,
    *,
    user_id: uuid.UUID | None,
    include_all: bool = False,
    offset: int = 0,
    limit: int = 50,
) -> tuple[list[EvaluationRunORM], int]:
    statement = select(EvaluationRunORM)
    if not include_all:
        statement = statement.where(EvaluationRunORM.user_id == user_id)
    total = session.scalar(select(func.count()).select_from(statement.subquery())) or 0
    statement = statement.order_by(EvaluationRunORM.created_at.desc()).offset(offset).limit(limit)
    return list(session.scalars(statement)), int(total)


def mark_evaluation_run_running(
    session: Session, run_id: uuid.UUID
) -> EvaluationRunORM:
    run = get_evaluation_run_for_update(session, run_id)
    if run is None:
        raise LookupError(f"Evaluation run {run_id} does not exist")
    if run.status in {"completed", "failed"}:
        return run
    run.status = "running"
    run.started_at = run.started_at or datetime.now(timezone.utc)
    session.flush()
    return run


def mark_evaluation_run_failed(
    session: Session, run_id: uuid.UUID, reason: str
) -> EvaluationRunORM:
    run = get_evaluation_run_for_update(session, run_id)
    if run is None:
        raise LookupError(f"Evaluation run {run_id} does not exist")
    if run.status == "completed":
        return run
    run.status = "failed"
    run.failure_reason = reason[:1000]
    run.ended_at = datetime.now(timezone.utc)
    if run.started_at is None:
        run.started_at = run.ended_at
    session.flush()
    return run


def upsert_evaluation_case_result(
    session: Session,
    *,
    run_id: uuid.UUID,
    dataset_case_id: str,
    **values: Any,
) -> EvaluationCaseResultORM:
    statement = insert(EvaluationCaseResultORM).values(
        run_id=run_id, dataset_case_id=dataset_case_id, **values
    )
    statement = statement.on_conflict_do_update(
        constraint="uq_evaluation_case_results_run_case",
        set_={
            "metric_scores": statement.excluded.metric_scores,
            "overall_score": statement.excluded.overall_score,
            "latency_ms": statement.excluded.latency_ms,
            "revision_iterations": statement.excluded.revision_iterations,
            "failure_reason": statement.excluded.failure_reason,
            "judge_metadata": statement.excluded.judge_metadata,
            "generated_result": statement.excluded.generated_result,
        },
    ).returning(EvaluationCaseResultORM)
    return session.scalars(statement, execution_options={"populate_existing": True}).one()


def create_evaluation_comparison(session: Session, **values: Any) -> EvaluationComparisonORM:
    comparison = EvaluationComparisonORM(**values)
    session.add(comparison)
    session.flush()
    return comparison


def get_evaluation_comparison(
    session: Session, comparison_id: uuid.UUID
) -> EvaluationComparisonORM | None:
    return session.get(EvaluationComparisonORM, comparison_id)


def list_evaluation_comparisons(
    session: Session,
    *,
    user_id: uuid.UUID | None,
    include_all: bool = False,
    offset: int = 0,
    limit: int = 50,
) -> tuple[list[EvaluationComparisonORM], int]:
    statement = select(EvaluationComparisonORM)
    if not include_all:
        statement = statement.where(EvaluationComparisonORM.user_id == user_id)
    total = session.scalar(select(func.count()).select_from(statement.subquery())) or 0
    statement = (
        statement.order_by(EvaluationComparisonORM.created_at.desc())
        .offset(offset)
        .limit(limit)
    )
    return list(session.scalars(statement)), int(total)


def list_comparisons_for_run(
    session: Session, run_id: uuid.UUID
) -> list[EvaluationComparisonORM]:
    return list(
        session.scalars(
            select(EvaluationComparisonORM).where(
                or_(
                    EvaluationComparisonORM.run_a_id == run_id,
                    EvaluationComparisonORM.run_b_id == run_id,
                )
            )
        )
    )
