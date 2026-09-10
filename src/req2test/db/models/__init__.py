"""Import all ORM models so Alembic can discover complete metadata."""

from .execution import ExecutionORM
from .evaluation import EvaluationCaseResultORM, EvaluationComparisonORM, EvaluationRunORM
from .knowledge_document import KnowledgeDocumentORM
from .task import TaskORM
from .test_case import TestCaseORM
from .user import UserORM

__all__ = [
    "ExecutionORM",
    "EvaluationCaseResultORM",
    "EvaluationComparisonORM",
    "EvaluationRunORM",
    "KnowledgeDocumentORM",
    "TaskORM",
    "TestCaseORM",
    "UserORM",
]
