"""Runtime configuration models."""

from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator


class LLMSettings(BaseModel):
    """Configuration for demo mode or an OpenAI-compatible endpoint."""

    mode: Literal["demo", "openai_compatible"] = "demo"
    model: str = "gpt-4.1-mini"
    api_key: str = ""
    base_url: str = "https://api.openai.com/v1"
    temperature: float = Field(default=0.1, ge=0.0, le=1.0)
    timeout_seconds: int = Field(default=90, ge=10, le=300)

    @field_validator("model")
    @classmethod
    def model_must_not_be_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("模型名称不能为空")
        return value


class GenerationConfig(BaseModel):
    """Controls test-case generation and the review loop."""

    include_positive: bool = True
    include_negative: bool = True
    include_edge: bool = False
    max_cases: int = Field(default=12, ge=1, le=60)
    min_review_score: int = Field(default=85, ge=60, le=100)
    max_review_iterations: int = Field(default=1, ge=0, le=3)

    @model_validator(mode="after")
    def at_least_one_test_type(self) -> "GenerationConfig":
        if not any([self.include_positive, self.include_negative, self.include_edge]):
            raise ValueError("至少选择一种测试类型")
        return self
