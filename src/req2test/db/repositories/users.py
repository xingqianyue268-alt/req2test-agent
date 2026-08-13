"""SQLAlchemy repository for authenticated users."""

from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..models import UserORM


VALID_ROLES = {"user", "admin"}


def normalize_email(email: str) -> str:
    normalized = email.strip().lower()
    local, separator, domain = normalized.rpartition("@")
    if not separator or not local or "." not in domain or len(normalized) > 255:
        raise ValueError("A valid email address is required")
    return normalized


def create_user(
    session: Session, *, email: str, password_hash: str, role: str = "user"
) -> UserORM:
    if role not in VALID_ROLES:
        raise ValueError("Role must be user or admin")
    user = UserORM(
        id=uuid.uuid4(),
        email=normalize_email(email),
        password_hash=password_hash,
        role=role,
        is_active=True,
    )
    session.add(user)
    session.flush()
    return user


def get_user_by_id(session: Session, user_id: uuid.UUID) -> UserORM | None:
    return session.get(UserORM, user_id)


def get_user_by_email(session: Session, email: str) -> UserORM | None:
    normalized = normalize_email(email)
    return session.scalar(select(UserORM).where(func.lower(UserORM.email) == normalized))


def update_user_role(session: Session, user: UserORM, role: str) -> UserORM:
    if role not in VALID_ROLES:
        raise ValueError("Role must be user or admin")
    user.role = role
    session.flush()
    return user


def set_user_active(session: Session, user: UserORM, is_active: bool) -> UserORM:
    user.is_active = is_active
    session.flush()
    return user


def list_users(
    session: Session, *, page: int = 1, page_size: int = 50
) -> tuple[list[UserORM], int]:
    total = session.scalar(select(func.count()).select_from(UserORM)) or 0
    records = list(
        session.scalars(
            select(UserORM)
            .order_by(UserORM.created_at.desc(), UserORM.id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    )
    return records, int(total)


def count_users(session: Session, *, active_only: bool = False) -> int:
    statement = select(func.count(UserORM.id))
    if active_only:
        statement = statement.where(UserORM.is_active.is_(True))
    return int(session.scalar(statement) or 0)


def lock_active_admins(session: Session) -> list[UserORM]:
    return list(
        session.scalars(
            select(UserORM)
            .where(UserORM.role == "admin", UserORM.is_active.is_(True))
            .order_by(UserORM.id)
            .with_for_update()
        )
    )
