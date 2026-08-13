"""Modern password hashing through pwdlib's recommended Argon2 configuration."""

from __future__ import annotations

from pwdlib import PasswordHash
from pwdlib.exceptions import UnknownHashError


MIN_PASSWORD_LENGTH = 8
MAX_PASSWORD_LENGTH = 128
_password_hash = PasswordHash.recommended()


class InvalidPassword(ValueError):
    """A password does not meet the deliberately small baseline policy."""


def validate_password(password: str) -> str:
    if len(password) < MIN_PASSWORD_LENGTH:
        raise InvalidPassword(f"Password must be at least {MIN_PASSWORD_LENGTH} characters")
    if len(password) > MAX_PASSWORD_LENGTH:
        raise InvalidPassword(f"Password must be at most {MAX_PASSWORD_LENGTH} characters")
    return password


def hash_password(password: str) -> str:
    return _password_hash.hash(validate_password(password))


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return _password_hash.verify(password, password_hash)
    except (UnknownHashError, ValueError):
        return False
