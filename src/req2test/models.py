"""Structured data contracts shared by the workflow."""

from typing import Literal

from pydantic import BaseModel, Field


class RequirementItem(BaseModel):
    requirement_id: str
    module: str = "通用模块"
    description: str
    acceptance_criteria: list[str] = Field(default_factory=list)


class TestStep(BaseModel):
    order: int
    action: str
    expected: str


class TestCase(BaseModel):
    case_id: str
    module: str
    title: str
    priority: Literal["P0", "P1", "P2", "P3"] = "P1"
    test_type: Literal["正向", "异常", "边界"] = "正向"
    preconditions: list[str] = Field(default_factory=list)
    steps: list[TestStep] = Field(default_factory=list)
    source_requirement: str
    rationale: str = ""


class ReviewReport(BaseModel):
    score: int = Field(ge=0, le=100)
    coverage_rate: float = Field(ge=0.0, le=1.0)
    issues: list[str] = Field(default_factory=list)
    suggestions: list[str] = Field(default_factory=list)


class WorkflowResult(BaseModel):
    requirements: list[RequirementItem]
    test_cases: list[TestCase]
    review: ReviewReport
    retrieved_context: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
