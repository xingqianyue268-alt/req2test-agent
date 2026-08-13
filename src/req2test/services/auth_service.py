"""Registration, authentication, and access-token orchestration."""

from __future__ import annotations

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..db.models import UserORM
from ..db.repositories import users
from ..security.passwords import hash_password, verify_password
from ..security.tokens import create_access_token


_DUMMY_PASSWORD_HASH = hash_password("timing-defense-password-not-used-by-any-account")


class DuplicateEmail(ValueError):
    pass


class InvalidCredentials(ValueError):
    pass


class InactiveAccount(ValueError):
    pass


class AuthService:
    def register(self, session: Session, *, email: str, password: str) -> UserORM:
        normalized = users.normalize_email(email)
        if users.get_user_by_email(session, normalized) is not None:
            raise DuplicateEmail("An account with this email already exists")
        try:
            user = users.create_user(
                session,
                email=normalized,
                password_hash=hash_password(password),
                role="user",
            )
            session.commit()
            session.refresh(user)
            return user
        except IntegrityError as exc:
            session.rollback()
            raise DuplicateEmail("An account with this email already exists") from exc

    def authenticate(self, session: Session, *, email: str, password: str) -> UserORM:
        try:
            user = users.get_user_by_email(session, email)
        except ValueError as exc:
            raise InvalidCredentials("Invalid email or password") from exc
        if user is None:
            verify_password(password, _DUMMY_PASSWORD_HASH)
            raise InvalidCredentials("Invalid email or password")
        if not verify_password(password, user.password_hash):
            raise InvalidCredentials("Invalid email or password")
        if not user.is_active:
            raise InactiveAccount("Account is inactive")
        return user

    def issue_access_token(self, user: UserORM) -> str:
        return create_access_token(str(user.id), role=user.role)
