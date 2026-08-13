from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import jwt
import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

import req2test.api as api_module
from req2test.cli.create_admin import (
    UpgradeConfirmationRequired,
    create_or_upgrade_admin,
)
from req2test.db.repositories import users
from req2test.db.session import get_db
from req2test.security.dependencies import require_roles
from req2test.security.passwords import hash_password, verify_password
from req2test.security.tokens import (
    InvalidAccessToken,
    create_access_token,
    decode_access_token,
)
from req2test.settings import Settings


PASSWORD = "correct horse battery staple"


def _settings(secret="a-secure-test-secret-that-is-long-enough"):
    return Settings(
        database_url="postgresql+psycopg://unused",
        db_pool_size=1,
        db_max_overflow=0,
        db_pool_timeout=1,
        environment="test",
        jwt_secret_key=secret,
        jwt_algorithm="HS256",
        jwt_access_token_expire_minutes=30,
        allow_anonymous_demo=True,
        auth_cookie_secure=False,
    )


def _client(db_session):
    def override_db():
        yield db_session

    api_module.app.dependency_overrides[get_db] = override_db
    return TestClient(api_module.app)


def _register(client, email="User@Example.COM "):
    return client.post(
        "/api/v1/auth/register", json={"email": email, "password": PASSWORD}
    )


def test_password_hash_and_verify():
    hashed = hash_password(PASSWORD)
    assert hashed.startswith("$argon2")
    assert PASSWORD not in hashed
    assert verify_password(PASSWORD, hashed) is True
    assert verify_password("wrong password", hashed) is False
    assert verify_password(PASSWORD, "not-a-recognized-hash") is False


def test_production_settings_reject_missing_default_and_short_jwt_secrets(monkeypatch):
    monkeypatch.setenv("REQ2TEST_ENV", "production")
    monkeypatch.delenv("JWT_SECRET_KEY", raising=False)
    with pytest.raises(ValueError, match="secure unique value"):
        Settings.from_env()

    monkeypatch.setenv("JWT_SECRET_KEY", "too-short")
    with pytest.raises(ValueError, match="at least 32 characters"):
        Settings.from_env()


def test_jwt_create_decode_expired_signature_and_type():
    settings = _settings()
    subject = str(uuid.uuid4())
    token = create_access_token(subject, role="admin", settings=settings)
    payload = decode_access_token(token, settings=settings)
    assert payload["sub"] == subject
    assert payload["type"] == "access"
    assert payload["role"] == "admin"
    assert payload["iat"] and payload["exp"] and uuid.UUID(payload["jti"])

    with pytest.raises(InvalidAccessToken):
        decode_access_token(token, settings=_settings("different-secure-test-secret-value"))

    expired = create_access_token(
        subject,
        settings=settings,
        now=datetime.now(timezone.utc) - timedelta(hours=2),
        expires_delta=timedelta(minutes=1),
    )
    with pytest.raises(InvalidAccessToken):
        decode_access_token(expired, settings=settings)

    claims = payload | {
        "type": "refresh",
        "iat": datetime.now(timezone.utc),
        "exp": datetime.now(timezone.utc) + timedelta(minutes=10),
    }
    wrong_type = jwt.encode(claims, settings.jwt_secret_key, algorithm="HS256")
    with pytest.raises(InvalidAccessToken):
        decode_access_token(wrong_type, settings=settings)


def test_register_normalizes_duplicate_and_never_accepts_admin_role(db_session):
    client = _client(db_session)
    try:
        response = _register(client)
        assert response.status_code == 201
        assert response.json() == {
            "id": response.json()["id"],
            "email": "user@example.com",
            "role": "user",
            "is_active": True,
        }
        assert "password" not in response.text
        assert "password_hash" not in response.text

        duplicate = _register(client, " USER@example.com")
        assert duplicate.status_code == 409

        injected = client.post(
            "/api/v1/auth/register",
            json={"email": "other@example.com", "password": PASSWORD, "role": "admin"},
        )
        assert injected.status_code == 422
    finally:
        api_module.app.dependency_overrides.clear()


def test_login_me_logout_and_authentication_failures(db_session):
    client = _client(db_session)
    try:
        registered = _register(client, "auth@example.com")
        assert registered.status_code == 201

        missing = client.post(
            "/api/v1/auth/login",
            json={"email": "missing@example.com", "password": PASSWORD},
        )
        wrong = client.post(
            "/api/v1/auth/login",
            json={"email": "auth@example.com", "password": "wrong password"},
        )
        assert missing.status_code == wrong.status_code == 401

        login = client.post(
            "/api/v1/auth/login",
            json={"email": "AUTH@example.com", "password": PASSWORD},
        )
        assert login.status_code == 200
        assert login.json()["token_type"] == "bearer"
        token = login.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}
        cookie_me = client.get("/api/v1/auth/me")
        assert cookie_me.status_code == 200
        me = client.get("/api/v1/auth/me", headers=headers)
        assert me.status_code == 200
        assert me.json()["email"] == "auth@example.com"
        assert "password_hash" not in me.text
        assert client.get("/workbench").status_code == 200
        assert client.post("/api/v1/auth/logout").json() == {"success": True}
        assert client.get("/api/v1/auth/me").status_code == 401

        user = users.get_user_by_email(db_session, "auth@example.com")
        users.set_user_active(db_session, user, False)
        db_session.commit()
        assert client.get("/api/v1/auth/me", headers=headers).status_code == 401
    finally:
        api_module.app.dependency_overrides.clear()


def test_malformed_missing_user_and_rbac_401_403_admin(db_session):
    app = FastAPI()

    @app.get("/admin")
    def admin_only(current=Depends(require_roles("admin"))):
        return {"email": current.email}

    def override_db():
        yield db_session

    app.dependency_overrides[get_db] = override_db
    client = TestClient(app)
    assert client.get("/admin").status_code == 401
    assert client.get("/admin", headers={"Authorization": "Bearer malformed"}).status_code == 401

    normal = users.create_user(
        db_session,
        email="normal@example.com",
        password_hash=hash_password(PASSWORD),
    )
    admin = users.create_user(
        db_session,
        email="admin@example.com",
        password_hash=hash_password(PASSWORD),
        role="admin",
    )
    db_session.commit()
    normal_token = create_access_token(str(normal.id), role="admin")
    admin_token = create_access_token(str(admin.id), role="user")
    assert client.get(
        "/admin", headers={"Authorization": f"Bearer {normal_token}"}
    ).status_code == 403
    assert client.get(
        "/admin", headers={"Authorization": f"Bearer {admin_token}"}
    ).status_code == 200

    missing_token = create_access_token(str(uuid.uuid4()))
    assert client.get(
        "/admin", headers={"Authorization": f"Bearer {missing_token}"}
    ).status_code == 401


def test_admin_bootstrap_create_requires_confirmation_and_upgrade(db_session):
    admin, action = create_or_upgrade_admin(
        db_session, email="root@example.com", password=PASSWORD
    )
    assert action == "created"
    assert admin.role == "admin"
    assert verify_password(PASSWORD, admin.password_hash)

    normal = users.create_user(
        db_session,
        email="promote@example.com",
        password_hash=hash_password(PASSWORD),
    )
    db_session.commit()
    with pytest.raises(UpgradeConfirmationRequired):
        create_or_upgrade_admin(
            db_session, email=normal.email, password="ignored password value"
        )
    promoted, action = create_or_upgrade_admin(
        db_session,
        email=normal.email,
        password="ignored password value",
        confirm_upgrade=True,
    )
    assert action == "upgraded"
    assert promoted.role == "admin"
