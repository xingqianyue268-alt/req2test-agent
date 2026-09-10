from __future__ import annotations

from decimal import Decimal

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from req2test.config import GenerationConfig, LLMSettings
from req2test.db.models import (
    EvaluationCaseResultORM,
    EvaluationComparisonORM,
    EvaluationRunORM,
)
from req2test.db.repositories import evaluations
from req2test.db.services.evaluation_persistence import EvaluationPersistenceService
from req2test.evaluation.dataset import load_golden_dataset
from req2test.evaluation.engine import evaluate_golden_dataset


def test_evaluation_run_case_results_and_comparison_are_persistent_and_idempotent(db_session):
    dataset = load_golden_dataset("evals/golden_demo.jsonl")
    service = EvaluationPersistenceService()
    generation = GenerationConfig(max_cases=30)
    settings = LLMSettings(mode="demo", model="demo-eval", seed=11)
    run_a = service.create_run(
        db_session,
        dataset=dataset,
        user_id=None,
        llm_settings=settings,
        generation_config=generation,
    )
    run_b = service.create_run(
        db_session,
        dataset=dataset,
        user_id=None,
        llm_settings=settings,
        generation_config=generation,
    )
    comparison = service.create_comparison(
        db_session,
        name="Demo A/B",
        user_id=None,
        dataset=dataset,
        run_a_id=run_a.id,
        run_b_id=run_b.id,
    )

    report_a = evaluate_golden_dataset(dataset, llm_settings=settings, generation_config=generation)
    report_b = evaluate_golden_dataset(dataset, llm_settings=settings, generation_config=generation)
    service.persist_report(db_session, run_a.id, report_a)
    service.persist_report(db_session, run_b.id, report_b)
    service.persist_report(db_session, run_a.id, report_a)
    service.refresh_comparison(db_session, comparison.id, (report_a, report_b))
    db_session.flush()

    loaded = evaluations.get_evaluation_run(db_session, run_a.id, include_cases=True)
    assert loaded.status == "completed"
    assert loaded.overall_score == Decimal(str(report_a.overall_score))
    assert loaded.seed == 11
    assert "api_key" not in str(loaded.judge_config)
    assert len(loaded.case_results) == len(dataset.cases)
    assert db_session.scalar(select(func.count(EvaluationCaseResultORM.id))) == (
        len(dataset.cases) * 2
    )
    stored_comparison = evaluations.get_evaluation_comparison(db_session, comparison.id)
    assert stored_comparison.status == "completed"
    assert stored_comparison.summary["overall"]["delta"] == 0.0


def test_evaluation_constraints_and_run_delete_cascade(db_session):
    dataset = load_golden_dataset("evals/golden_demo.jsonl")
    service = EvaluationPersistenceService()
    settings = LLMSettings(mode="demo")
    generation = GenerationConfig(max_cases=30)
    run_a = service.create_run(
        db_session,
        dataset=dataset,
        user_id=None,
        llm_settings=settings,
        generation_config=generation,
    )
    run_b = service.create_run(
        db_session,
        dataset=dataset,
        user_id=None,
        llm_settings=settings,
        generation_config=generation,
    )
    comparison = service.create_comparison(
        db_session,
        name="Cascade check",
        user_id=None,
        dataset=dataset,
        run_a_id=run_a.id,
        run_b_id=run_b.id,
    )
    report = evaluate_golden_dataset(dataset, generation_config=generation)
    service.persist_report(db_session, run_a.id, report)
    db_session.flush()

    first_case = run_a.case_results[0]
    with pytest.raises(IntegrityError), db_session.begin_nested():
        db_session.add(
            EvaluationCaseResultORM(
                run_id=run_a.id,
                dataset_case_id=first_case.dataset_case_id,
                metric_scores={},
                overall_score=0,
                latency_ms=0,
                judge_metadata={},
            )
        )
        db_session.flush()

    run_a_id = run_a.id
    comparison_id = comparison.id
    db_session.delete(run_a)
    db_session.flush()
    assert db_session.get(EvaluationRunORM, run_a_id) is None
    assert db_session.scalar(
        select(func.count(EvaluationCaseResultORM.id)).where(
            EvaluationCaseResultORM.run_id == run_a_id
        )
    ) == 0
    assert db_session.scalar(
        select(func.count(EvaluationComparisonORM.id)).where(
            EvaluationComparisonORM.id == comparison_id
        )
    ) == 0
