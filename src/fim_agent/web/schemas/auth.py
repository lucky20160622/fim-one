"""Authentication request/response schemas."""

from __future__ import annotations

from pydantic import BaseModel, Field


class UserInfo(BaseModel):
    id: str
    username: str
    is_admin: bool


class RegisterRequest(BaseModel):
    username: str = Field(min_length=2, max_length=50)
    password: str = Field(min_length=6, max_length=100)


class LoginRequest(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int  # seconds
    user: UserInfo


class RefreshRequest(BaseModel):
    refresh_token: str
