"""Authenticated HTTP surface for the Evaluation Center."""

from __future__ import annotations

import os
import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from .config import GenerationConfig, LLMSettings
from .db.models import UserORM
from .db.repositories import evaluations
from .db.session import get_db
from .evaluation.dataset import DatasetLoadError
from .evaluation.tasks import run_evaluation
from .evaluation_ui import render_evaluations_html
from .security.dependencies import get_current_user
from .services.evaluation_service import (
    EvaluationDispatchError,
    EvaluationService,
    comparison_dto,
    dataset_dto,
    run_dto,
)

router = APIRouter()
DatabaseSession = Annotated[Session, Depends(get_db)]
CurrentUser = Annotated[UserORM, Depends(get_current_user)]
PageNumber = Annotated[int, Query(ge=1)]
PageSize = Annotated[int, Query(ge=1, le=100)]


def _publish_evaluation(args: list[Any], eager: bool) -> str:
    result = run_evaluation.apply(args=args) if eager else run_evaluation.delay(*args)
    return str(result.id or args[0])


evaluation_service = EvaluationService(_publish_evaluation)


class EvaluationConfigurationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    llm_settings: LLMSettings = Field(default_factory=LLMSettings)
    generation_config: GenerationConfig = Field(default_factory=GenerationConfig)
    judge_settings: LLMSettings | None = None


class EvaluationRunCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    dataset_name: str = Field(min_length=1, max_length=128)
    configuration: EvaluationConfigurationRequest = Field(
        default_factory=EvaluationConfigurationRequest
    )


class EvaluationComparisonCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=255)
    dataset_name: str = Field(min_length=1, max_length=128)
    configuration_a: EvaluationConfigurationRequest
    configuration_b: EvaluationConfigurationRequest


def _eager_evaluations() -> bool:
    return os.getenv("REQ2TEST_EAGER_EVALUATIONS", "false").lower() in {
        "1",
        "true",
        "yes",
    }


def _can_read(owner_id: uuid.UUID | None, current_user: UserORM) -> bool:
    return current_user.role == "admin" or owner_id == current_user.id


@router.get("/evaluations", response_class=HTMLResponse, include_in_schema=False)
def evaluations_page(request: Request, db: DatabaseSession):
    from .api import _login_redirect, _web_user

    if _web_user(request, db) is None:
        return _login_redirect(request)
    return render_evaluations_html()


@router.get("/api/v1/evaluations/datasets")
def list_evaluation_datasets(
    _current_user: CurrentUser,
) -> dict[str, Any]:
    try:
        items = [dataset_dto(dataset) for dataset in evaluation_service.registry.list()]
    except DatasetLoadError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return {"items": items, "total": len(items)}


@router.post("/api/v1/evaluations/runs", status_code=202)
def create_evaluation_run(
    request: EvaluationRunCreateRequest,
    db: DatabaseSession,
    current_user: CurrentUser,
) -> dict[str, Any]:
    configuration = request.configuration
    try:
        run = evaluation_service.create_and_dispatch(
            db,
            dataset_name=request.dataset_name,
            user_id=current_user.id,
            llm_settings=configuration.llm_settings,
            generation_config=configuration.generation_config,
            judge_settings=configuration.judge_settings,
            eager=_eager_evaluations(),
        )
    except DatasetLoadError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except EvaluationDispatchError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return {
        "run": run_dto(run),
        "status_url": f"/api/v1/evaluations/runs/{run.id}",
    }


@router.get("/api/v1/evaluations/runs")
def list_evaluation_runs(
    db: DatabaseSession,
    current_user: CurrentUser,
    page: PageNumber = 1,
    page_size: PageSize = 20,
) -> dict[str, Any]:
    items, total = evaluations.list_evaluation_runs(
        db,
        user_id=current_user.id,
        include_all=current_user.role == "admin",
        offset=(page - 1) * page_size,
        limit=page_size,
    )
    return {
        "items": [run_dto(item) for item in items],
        "page": page,
        "page_size": page_size,
        "total": total,
    }


@router.get("/api/v1/evaluations/runs/{run_id}")
def get_evaluation_run(
    run_id: uuid.UUID,
    db: DatabaseSession,
    current_user: CurrentUser,
) -> dict[str, Any]:
    run = evaluations.get_evaluation_run(db, run_id, include_cases=True)
    if run is None or not _can_read(run.user_id, current_user):
        raise HTTPException(status_code=404, detail="Evaluation run not found")
    return run_dto(run, include_cases=True)


@router.post("/api/v1/evaluations/comparisons", status_code=202)
def create_evaluation_comparison(
    request: EvaluationComparisonCreateRequest,
    db: DatabaseSession,
    current_user: CurrentUser,
) -> dict[str, Any]:
    a = request.configuration_a
    b = request.configuration_b
    try:
        comparison = evaluation_service.create_comparison_and_dispatch(
            db,
            name=request.name,
            dataset_name=request.dataset_name,
            user_id=current_user.id,
            configuration_a=(a.llm_settings, a.generation_config, a.judge_settings),
            configuration_b=(b.llm_settings, b.generation_config, b.judge_settings),
            eager=_eager_evaluations(),
        )
    except DatasetLoadError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except EvaluationDispatchError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return {
        "comparison": comparison_dto(comparison),
        "status_url": f"/api/v1/evaluations/comparisons/{comparison.id}",
    }


@router.get("/api/v1/evaluations/comparisons")
def list_evaluation_comparisons(
    db: DatabaseSession,
    current_user: CurrentUser,
    page: PageNumber = 1,
    page_size: PageSize = 20,
) -> dict[str, Any]:
    items, total = evaluations.list_evaluation_comparisons(
        db,
        user_id=current_user.id,
        include_all=current_user.role == "admin",
        offset=(page - 1) * page_size,
        limit=page_size,
    )
    return {
        "items": [comparison_dto(item) for item in items],
        "page": page,
        "page_size": page_size,
        "total": total,
    }


@router.get("/api/v1/evaluations/comparisons/{comparison_id}")
def get_evaluation_comparison(
    comparison_id: uuid.UUID,
    db: DatabaseSession,
    current_user: CurrentUser,
) -> dict[str, Any]:
    comparison = evaluations.get_evaluation_comparison(db, comparison_id)
    if comparison is None or not _can_read(comparison.user_id, current_user):
        raise HTTPException(status_code=404, detail="Evaluation comparison not found")
    run_a = evaluations.get_evaluation_run(db, comparison.run_a_id)
    run_b = evaluations.get_evaluation_run(db, comparison.run_b_id)
    return {
        **comparison_dto(comparison),
        "configuration_a": run_dto(run_a) if run_a else None,
        "configuration_b": run_dto(run_b) if run_b else None,
    }
