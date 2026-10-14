"""Real PostgreSQL checks for P0 public-result and legacy-read boundaries."""

import json
import uuid

from sqlalchemy import select

from req2test.config import GenerationConfig, LLMSettings
from req2test.db.models import ExecutionORM
from req2test.db.repositories import tasks
from req2test.db.services.evaluation_persistence import EvaluationPersistenceService
from req2test.db.services.result_persistence import ResultPersistenceService
from req2test.db.services.task_persistence import TaskPersistenceService
from req2test.evaluation.dataset import load_golden_dataset
from req2test.evaluation.engine import evaluate_golden_dataset
from req2test.services.evaluation_service import run_dto
from req2test.task_store import TaskStore


def test_execution_database_and_legacy_diagnostic_reads_are_redacted(db_session):
    task = tasks.create_task(
        db_session,
        id=uuid.uuid4(),
        title="local",
        requirement_text="local",
        status="queued",
        stage="queued",
        progress=0,
        state_version=1,
        generation_config={},
        execution_config={},
    )
    db_session.flush()
    secret = "SYNTHETIC_DATABASE_SECRET"
    payload = {
        "execution": {
            "http_results": [
                {
                    "case_id": "ONE",
                    "method": "GET",
                    "url": "http://localhost/",
                    "passed": True,
                    "expected_status": 200,
                    "status_code": 200,
                    "response_excerpt": json.dumps({"token": secret, "status": "ok"}),
                }
            ],
            "diagnostic_evidence": [{"details": {"stdout": json.dumps({"Cookie": secret})}}],
        }
    }
    ResultPersistenceService().finalize_completed(db_session, str(task.id), payload)
    db_session.flush()
    db_session.refresh(task)
    row = db_session.scalar(select(ExecutionORM).where(ExecutionORM.task_id == task.id))
    assert secret not in row.response_excerpt
    assert secret not in json.dumps(task.result_payload)
    # Legacy records must not leak through diagnostics even before a data cleanup.
    task.result_payload = payload
    db_session.flush()
    service = TaskPersistenceService(
        TaskStore(redis_url="redis://127.0.0.1:1/0"), lambda *a: "unused"
    )
    for read in [service.get_task_state, service.get_task_detail, service.get_task_diagnostics]:
        result = read(db_session, str(task.id), is_admin=True)
        assert result and secret not in json.dumps(result)
    assert secret in json.dumps(payload), "Caller execution inputs are not mutated"


def test_evaluation_database_and_export_do_not_store_sensitive_evidence(db_session):
    dataset = load_golden_dataset("evals/golden_demo.jsonl")
    service = EvaluationPersistenceService()
    settings = LLMSettings(mode="demo")
    generation = GenerationConfig(max_cases=30)
    run = service.create_run(
        db_session,
        dataset=dataset,
        user_id=None,
        llm_settings=settings,
        generation_config=generation,
    )
    report = evaluate_golden_dataset(dataset, llm_settings=settings, generation_config=generation)
    report.cases[0].generated_result["errors"] = ['{"token":"SYNTHETIC_EVALUATION_SECRET"}']
    service.persist_report(db_session, run.id, report)
    db_session.flush()
    db_session.refresh(run)
    assert "SYNTHETIC_EVALUATION_SECRET" not in json.dumps(run.case_results[0].generated_result)
    assert "SYNTHETIC_EVALUATION_SECRET" not in json.dumps(run_dto(run, include_cases=True))
    assert "SYNTHETIC_EVALUATION_SECRET" not in report.model_dump_json()
