from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import List, Optional, Tuple
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from timz_app.core.config import settings
from timz_app.core.jwt import (
    create_access_token,
    create_refresh_token,
    hash_refresh_token,
    issue_refresh_token,
)
from timz_app.dependencies.firebase import verify_firebase_id_token_or_401
from timz_app.models.refresh_token import RefreshToken
from timz_app.models.role import Role
from timz_app.models.user import User
from timz_app.models.user_role import UserRole
from timz_app.services.user_service import upsert_user_from_claims_async

UTC = timezone.utc


async def _get_user_role_names(session: AsyncSession, user_id: UUID) -> List[str]:
    """
    Return role names for a given user_id, ordered by name.
    """
    result = await session.execute(
        select(Role.name)
        .join(UserRole, UserRole.role_id == Role.id)
        .where(UserRole.user_id == user_id)
        .order_by(Role.name)
    )
    return list(result.scalars().all())


async def exchange_firebase_id_token(
    session: AsyncSession,
    id_token: str,
    default_roles: tuple[str, ...] = ("client",),
    user_agent: str | None = None,
    ip: str | None = None,
    single_device: bool = False,
) -> Tuple[str, str, UUID, str | None, list[str]]:
    """
    Verify a Firebase ID token, upsert the user, ensure default roles, then
    issue a short-lived access token (JWT HS256) and a revocable refresh token.

    Returns:
        (access_token, refresh_token_raw, user_id, user_email, role_names)
    Raises:
        fastapi.HTTPException (401) if Firebase token invalid
        any DB exception for persistence issues
    """
    # 1) Verify Firebase token (raises 401 on invalid)
    claims = verify_firebase_id_token_or_401(id_token)

    # 2) Upsert user from claims (create on first visit, ensure default role(s))
    user = await upsert_user_from_claims_async(
        session=session,
        claims=claims,
        default_role_names=default_roles,
        extra_role_names=(),  # can be enriched later by business rules
    )

    # 3) Roles to embed in access JWT + return
    role_names = await _get_user_role_names(session, user.id)

    # 4) Issue tokens
    access_token = create_access_token(sub=str(user.id), roles=role_names)
    refresh_raw, _rt = await issue_refresh_token(
        session=session,
        user_id=user.id,
        user_agent=user_agent,
        ip=ip,
        single_device=single_device,  # set True if you want one device policy
    )

    return access_token, refresh_raw, user.id, user.email, role_names


async def refresh_access_token_from_raw(
    session: AsyncSession,
    raw_refresh_token: str,
    *,
    rotate: bool = True,
    user_agent: Optional[str] = None,
    ip: Optional[str] = None,
) -> Tuple[str, Optional[str], str, List[str]]:
    """
    Validate a refresh token, issue a new access token, and optionally rotate refresh.

    Returns: (access_token, new_refresh_token_or_None, user_id, roles)
    Raises 401 if token unknown/expired/revoked.
    """
    if not raw_refresh_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="missing_refresh_token"
        )

    token_hash = hash_refresh_token(raw_refresh_token)

    # Load refresh token row
    rt: RefreshToken | None = (
        await session.scalars(
            select(RefreshToken).where(RefreshToken.token_hash == token_hash)
        )
    ).first()

    now = datetime.now(UTC)
    if not rt:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="refresh_unknown"
        )
    if rt.revoked_at is not None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="refresh_revoked"
        )
    if rt.expires_at <= now:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="refresh_expired"
        )

    user_id = rt.user_id

    # Load roles for access token
    roles = await _get_user_role_names(session, user_id)

    # Issue new access token
    access = create_access_token(sub=str(user_id), roles=roles)

    new_refresh_raw: Optional[str] = None

    if rotate:
        # Revoke current
        rt.revoked_at = now

        # Create & persist a new refresh token
        new_refresh_raw = create_refresh_token(sub=str(user_id))
        new_hash = hash_refresh_token(new_refresh_raw)
        new_expires = now + timedelta(days=int(settings.REFRESH_TTL_DAYS))

        session.add(
            RefreshToken(
                user_id=user_id,
                token_hash=new_hash,
                expires_at=new_expires,
                user_agent=user_agent,
                ip=ip,
            )
        )
        await session.commit()
    else:
        # No rotation → keep same refresh
        await session.commit()

    return access, new_refresh_raw, str(user_id), roles
