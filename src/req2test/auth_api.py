"""Authentication API routes and response contracts."""

from __future__ import annotations

from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from .db.models import UserORM
from .db.session import get_db
from .security.dependencies import get_current_user
from .services.auth_service import (
    AuthService,
    DuplicateEmail,
    InactiveAccount,
    InvalidCredentials,
)
from .settings import get_settings


router = APIRouter(prefix="/api/v1/auth", tags=["authentication"])
auth_service = AuthService()


class RegisterRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: str = Field(min_length=3, max_length=255)
    password: str = Field(min_length=8, max_length=128)


class LoginRequest(RegisterRequest):
    pass


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    email: str
    role: Literal["user", "admin"]
    is_active: bool

    @classmethod
    def from_user(cls, user: UserORM) -> "UserResponse":
        return cls(
            id=str(user.id),
            email=user.email,
            role=user.role,
            is_active=user.is_active,
        )


class TokenResponse(BaseModel):
    access_token: str
    token_type: Literal["bearer"] = "bearer"
    user: UserResponse


@router.post("/register", response_model=UserResponse, status_code=201)
def register(request: RegisterRequest, db: Annotated[Session, Depends(get_db)]) -> UserResponse:
    try:
        user = auth_service.register(db, email=request.email, password=request.password)
    except DuplicateEmail as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return UserResponse.from_user(user)


@router.post("/login", response_model=TokenResponse)
def login(
    request: LoginRequest,
    response: Response,
    db: Annotated[Session, Depends(get_db)],
) -> TokenResponse:
    try:
        user = auth_service.authenticate(db, email=request.email, password=request.password)
    except InvalidCredentials as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    except InactiveAccount as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    token = auth_service.issue_access_token(user)
    settings = get_settings()
    response.set_cookie(
        "req2test_access_token",
        token,
        max_age=settings.jwt_access_token_expire_minutes * 60,
        httponly=True,
        secure=settings.auth_cookie_secure,
        samesite="lax",
        path="/",
    )
    return TokenResponse(
        access_token=token,
        user=UserResponse.from_user(user),
    )


@router.get("/me", response_model=UserResponse)
def me(current_user: Annotated[UserORM, Depends(get_current_user)]) -> UserResponse:
    return UserResponse.from_user(current_user)


@router.post("/logout")
def logout(response: Response) -> dict[str, bool]:
    """End the browser session by clearing the stateless access-token cookie."""

    response.delete_cookie("req2test_access_token", path="/", samesite="lax")
    return {"success": True}
