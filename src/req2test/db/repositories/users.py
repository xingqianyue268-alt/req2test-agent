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
