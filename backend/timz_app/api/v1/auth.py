from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Header, Query, Request
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from timz_app.core.jwt import (  # si tu n'as pas ce wrapper, ajoute la fonction hash_refresh_token dans core/jwt.py (voir §2)
    create_access_token,
    issue_refresh_token,
    revoke_all_user_refresh,
    revoke_refresh_token,
)
from timz_app.core.security import get_current_user_db
from timz_app.db.database import get_db
from timz_app.models.refresh_token import RefreshToken
from timz_app.models.user import User
from timz_app.schemas.auth import (
    AuthExchangeRequest,
    AuthRefreshRequest,
    AuthRefreshResponse,
    AuthTokensResponse,
    TokenUserOut,
)
from timz_app.services.auth_service import (
    _get_user_role_names,
    exchange_firebase_id_token,
    refresh_access_token_from_raw,
)


class RefreshRequest(BaseModel):
    refresh_token: str


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


router = APIRouter(prefix="/auth", tags=["auth"])


def _extract_ip(req: Request) -> str | None:
    """Best-effort client IP (prefers X-Forwarded-For, falls back to req.client.host)."""
    xff = req.headers.get("x-forwarded-for")
    if xff:
        return xff.split(",")[0].strip()
    return req.client.host if req.client else None


@router.get(
    "/me",
    response_model=TokenUserOut,
    summary="Return current user (access token required)",
)
async def auth_me(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user_db),
):
    """
    Return the current authenticated user info and roles.
    Requires a valid **access token** in `Authorization: Bearer ...`.
    """
    roles = await _get_user_role_names(db, user.id)
    return TokenUserOut(id=user.id, email=user.email, roles=roles)


@router.post("/logout", summary="Logout: revoke all refresh tokens for current user")
async def auth_logout(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user_db),
):
    """
    Logout the current user by **revoking all** of their refresh tokens.
    Access token remains valid until it naturally expires.
    Returns the number of revoked refresh tokens.
    """
    count = await revoke_all_user_refresh(db, user.id)
    return {"revoked": count}


@router.post(
    "/exchange",
    response_model=AuthTokensResponse,
    summary="Exchange Firebase ID token for our tokens",
)
async def auth_exchange(
    body: AuthExchangeRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user_agent: str | None = Header(None, alias="User-Agent"),
):
    """
    Exchange a **Firebase ID token** (Google SecureToken) for **our tokens**.

    Workflow:
      1) Verify Firebase ID token (issuer/audience/signature).
      2) Upsert user in DB + ensure default role(s) (e.g., 'client').
      3) Issue short-lived **access JWT** (HS256) carrying `sub` and `roles`.
      4) Issue revocable **refresh token** (opaque) and persist its hash.

    Returns:
      - `access_token` (string, Authorization: Bearer ... for API calls)
      - `refresh_token` (string; in production, prefer httpOnly+Secure cookie)
      - `user` (id/email/roles)
    """
    ip = _extract_ip(request)
    access, refresh, user_id, email, role_names = await exchange_firebase_id_token(
        session=db,
        id_token=body.id_token,
        default_roles=("client",),
        user_agent=user_agent,
        ip=ip,
        single_device=False,  # set True if you want one device policy
    )
    return AuthTokensResponse(
        access_token=access,
        refresh_token=refresh,
        user=TokenUserOut(id=user_id, email=email, roles=role_names),
    )


@router.post(
    "/refresh",
    response_model=AuthRefreshResponse,
    summary="Refresh access token (optionally rotate)",
)
async def auth_refresh(
    body: AuthRefreshRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user_agent: str | None = Header(None, alias="User-Agent"),
    rotate: bool = Query(True),
):
    """
    Validate the provided refresh token and issue a new access token.
    If `rotate=true` (default), revoke the used refresh and return a new refresh token.
    """
    ip = request.headers.get(
        "x-forwarded-for", (request.client.host if request.client else None)
    )
    access, new_refresh, _user_id, _roles = await refresh_access_token_from_raw(
        session=db,
        raw_refresh_token=(body.refresh_token or "").strip(),
        rotate=rotate,
        user_agent=user_agent,
        ip=ip,
    )
    return AuthRefreshResponse(access_token=access, refresh_token=new_refresh)
