from __future__ import annotations

from contextlib import contextmanager

import pytest
from sqlalchemy import func, select

import req2test.evaluation.tasks as task_module
from req2test.config import GenerationConfig, LLMSettings
from req2test.db.models import EvaluationCaseResultORM
from req2test.db.repositories import evaluations
from req2test.db.services.evaluation_persistence import EvaluationPersistenceService
from req2test.evaluation.dataset import load_golden_dataset


def _scope(db_session):
    @contextmanager
    def session_scope():
        try:
            yield db_session
            db_session.flush()
        except Exception:
            db_session.rollback()
            raise

    return session_scope


def _arguments(run_id, dataset, settings, generation, identifier, digest):
    return (
        str(run_id),
        dataset.name,
        dataset.digest,
        settings.model_dump(),
        generation.model_dump(),
        settings.model_dump(),
        identifier,
        digest,
    )


def test_evaluation_worker_success_and_duplicate_delivery_are_idempotent(
    db_session, monkeypatch
):
    dataset = load_golden_dataset("evals/golden_demo.jsonl")
    settings = LLMSettings(mode="demo", model="worker-demo", seed=17)
    generation = GenerationConfig(max_cases=30)
    identifier = "test-knowledge-v1"
    digest = "a" * 64
    run = EvaluationPersistenceService().create_run(
        db_session,
        dataset=dataset,
        user_id=None,
        llm_settings=settings,
        generation_config=generation,
        knowledge_base_identifier=identifier,
        knowledge_base_digest=digest,
    )
    db_session.flush()
    monkeypatch.setattr(task_module, "session_scope", _scope(db_session))
    monkeypatch.setattr(
        task_module, "current_knowledge_snapshot", lambda _session: (identifier, digest)
    )

    arguments = _arguments(run.id, dataset, settings, generation, identifier, digest)
    first = task_module.run_evaluation.run(*arguments)
    initial_count = db_session.scalar(select(func.count(EvaluationCaseResultORM.id)))
    second = task_module.run_evaluation.run(*arguments)

    db_session.expire_all()
    stored = evaluations.get_evaluation_run(db_session, run.id, include_cases=True)
    assert first["status"] == second["status"] == "completed"
    assert stored.status == "completed"
    assert len(stored.case_results) == len(dataset.cases)
    assert all(
        set(case.generated_result) == {
            "requirements",
            "test_cases",
            "review",
            "review_iterations",
        }
        for case in stored.case_results
    )
    assert initial_count == len(dataset.cases)
    assert db_session.scalar(select(func.count(EvaluationCaseResultORM.id))) == initial_count


def test_evaluation_worker_failure_is_terminal_and_redacted(db_session, monkeypatch):
    dataset = load_golden_dataset("evals/golden_demo.jsonl")
    settings = LLMSettings(mode="demo")
    generation = GenerationConfig(max_cases=30)
    identifier = "test-knowledge-v1"
    digest = "b" * 64
    run = EvaluationPersistenceService().create_run(
        db_session,
        dataset=dataset,
        user_id=None,
        llm_settings=settings,
        generation_config=generation,
        knowledge_base_identifier=identifier,
        knowledge_base_digest=digest,
    )
    db_session.flush()
    monkeypatch.setattr(task_module, "session_scope", _scope(db_session))

    arguments = list(_arguments(run.id, dataset, settings, generation, identifier, digest))
    arguments[2] = "0" * 64
    with pytest.raises(ValueError, match="dataset digest changed"):
        task_module.run_evaluation.run(*arguments)

    db_session.expire_all()
    stored = evaluations.get_evaluation_run(db_session, run.id, include_cases=True)
    assert stored.status == "failed"
    assert stored.failure_reason == "Golden dataset digest changed after this run was queued"
    assert stored.case_results == []
