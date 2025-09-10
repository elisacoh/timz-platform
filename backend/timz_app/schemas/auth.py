from __future__ import annotations

from typing import List, Optional
from uuid import UUID

from pydantic import BaseModel, Field


class AuthExchangeRequest(BaseModel):
    """Request body for /auth/exchange: carries a Firebase ID token."""

    id_token: str = Field(
        ..., description="Firebase ID token (from signInWithPassword / signInWithPopup)"
    )


class TokenUserOut(BaseModel):
    """Minimal user payload returned to the client alongside tokens."""

    id: UUID
    email: str | None = None
    roles: List[str] = Field(default_factory=list)


class AuthTokensResponse(BaseModel):
    """
    Response for /auth/exchange:
    - access_token: short-lived JWT (HS256) carrying sub + roles
    - refresh_token: opaque string (only in dev as body; prod: cookie httpOnly)
    - user: minimal user information for client context
    """

    access_token: str
    refresh_token: str
    user: TokenUserOut


class AuthRefreshRequest(BaseModel):
    refresh_token: str


class AuthRefreshResponse(BaseModel):
    access_token: str
    refresh_token: Optional[str] = None
