"""Administrative product operations with transactional safety invariants."""

from __future__ import annotations

import math
import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db.models import TaskORM, UserORM
from ..db.repositories import users
from ..db.repositories.tasks import search_tasks
from ..db.services.task_persistence import task_to_list_item


class LastActiveAdminError(RuntimeError):
    pass


def user_dto(user: UserORM) -> dict[str, Any]:
    return {
        "id": str(user.id),
        "email": user.email,
        "role": user.role,
        "is_active": user.is_active,
        "created_at": user.created_at,
        "updated_at": user.updated_at,
    }


class AdminService:
    def dashboard(self, session: Session) -> dict[str, Any]:
        tasks = list(session.scalars(select(TaskORM)))
        completed = [task for task in tasks if task.status == "completed"]
        failed = [task for task in tasks if task.status == "failed"]
        pass_rates = [
            float(task.result_summary["http_pass_rate"])
            for task in tasks
            if task.result_summary and task.result_summary.get("http_pass_rate") is not None
        ]
        recent, _ = search_tasks(session, include_all=True, limit=8)
        return {
            "metrics": {
                "total_users": users.count_users(session),
                "active_users": users.count_users(session, active_only=True),
                "total_tasks": len(tasks),
                "completed_tasks": len(completed),
                "failed_tasks": len(failed),
                "http_pass_rate": (
                    round(sum(pass_rates) / len(pass_rates), 4) if pass_rates else None
                ),
            },
            "recent_tasks": [task_to_list_item(task, include_user=True) for task in recent],
        }

    def list_users(self, session: Session, *, page: int, page_size: int) -> dict[str, Any]:
        records, total = users.list_users(session, page=page, page_size=page_size)
        return {
            "items": [user_dto(record) for record in records],
            "page": page,
            "page_size": page_size,
            "total": total,
            "pages": math.ceil(total / page_size) if total else 0,
        }

    def _locked_user(self, session: Session, user_id: uuid.UUID) -> UserORM | None:
        return session.scalar(select(UserORM).where(UserORM.id == user_id).with_for_update())

    def set_status(
        self, session: Session, *, user_id: uuid.UUID, is_active: bool
    ) -> UserORM | None:
        active_admins = users.lock_active_admins(session)
        target = self._locked_user(session, user_id)
        if target is None:
            return None
        if target.role == "admin" and target.is_active and not is_active and len(active_admins) <= 1:
            session.rollback()
            raise LastActiveAdminError("The last active admin cannot be disabled")
        users.set_user_active(session, target, is_active)
        session.commit()
        return target

    def set_role(self, session: Session, *, user_id: uuid.UUID, role: str) -> UserORM | None:
        active_admins = users.lock_active_admins(session)
        target = self._locked_user(session, user_id)
        if target is None:
            return None
        if (
            target.role == "admin"
            and target.is_active
            and role != "admin"
            and len(active_admins) <= 1
        ):
            session.rollback()
            raise LastActiveAdminError("The last active admin cannot be demoted")
        users.update_user_role(session, target, role)
        session.commit()
        return target
