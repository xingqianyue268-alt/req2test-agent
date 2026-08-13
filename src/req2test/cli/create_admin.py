"""Interactive, non-default administrative account bootstrap."""

from __future__ import annotations

import argparse
import getpass

from dotenv import load_dotenv
from sqlalchemy.orm import Session

from ..db.models import UserORM
from ..db.repositories import users
from ..security.passwords import hash_password


class UpgradeConfirmationRequired(ValueError):
    pass


def create_or_upgrade_admin(
    session: Session,
    *,
    email: str,
    password: str,
    confirm_upgrade: bool = False,
) -> tuple[UserORM, str]:
    normalized = users.normalize_email(email)
    existing = users.get_user_by_email(session, normalized)
    if existing is not None:
        if existing.role == "admin":
            return existing, "already_admin"
        if not confirm_upgrade:
            raise UpgradeConfirmationRequired(
                "The account exists as a normal user; explicit confirmation is required"
            )
        users.update_user_role(session, existing, "admin")
        session.commit()
        session.refresh(existing)
        return existing, "upgraded"

    admin = users.create_user(
        session,
        email=normalized,
        password_hash=hash_password(password),
        role="admin",
    )
    session.commit()
    session.refresh(admin)
    return admin, "created"


def main() -> None:
    load_dotenv()
    # Import after loading .env so the module-level SQLAlchemy engine uses DATABASE_URL.
    from ..db.session import SessionLocal

    parser = argparse.ArgumentParser(description="Create or explicitly promote an admin")
    parser.add_argument("--email", help="Admin email; prompted when omitted")
    args = parser.parse_args()
    email = (args.email or input("Admin email: ")).strip()
    password = getpass.getpass("Admin password: ")
    confirmation = getpass.getpass("Confirm password: ")
    if password != confirmation:
        raise SystemExit("Passwords do not match")

    with SessionLocal() as session:
        existing = users.get_user_by_email(session, email)
        confirm_upgrade = False
        if existing is not None and existing.role != "admin":
            answer = input("Existing normal user. Promote to admin? [y/N]: ").strip().lower()
            confirm_upgrade = answer in {"y", "yes"}
        try:
            user, action = create_or_upgrade_admin(
                session,
                email=email,
                password=password,
                confirm_upgrade=confirm_upgrade,
            )
        except UpgradeConfirmationRequired as exc:
            raise SystemExit(str(exc)) from exc
    print(f"Admin {action}: {user.email}")


if __name__ == "__main__":
    main()
