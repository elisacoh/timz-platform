# timz_app/core/jwt.py
from __future__ import annotations

import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone
from typing import Sequence, Tuple

import jwt  # PyJWT
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from timz_app.core.config import settings
from timz_app.models.refresh_token import RefreshToken

ALGO = "HS256"

__all__ = [
    "create_access_token",
    "verify_access_token",
    "create_refresh_token_raw",
    "issue_refresh_token",
    "verify_refresh_token",
    "revoke_refresh_token",
    "revoke_all_user_refresh",
    "hash_refresh_token",
    "create_refresh_token",
]


# -- Public shims to align with service imports --


def hash_refresh_token(raw: str) -> str:
    """
    Public wrapper around the internal _hash_refresh.
    Keeps services decoupled from private names.
    """
    return _hash_refresh(raw)


def create_refresh_token(sub: str | None = None, ttl_days: int | None = None) -> str:
    """
    Public helper that returns an opaque refresh token string (not persisted).
    Most services should prefer `issue_refresh_token(session, user_id, ...)`
    which also persists the hash in DB. This shim exists for compatibility
    with older code expecting create_refresh_token().
    """
    # You can ignore sub/ttl_days here; persistence decides actual TTL.
    return create_refresh_token_raw()


# ---------- utils temps ----------
def _now() -> datetime:
    return datetime.now(timezone.utc)


def _ts(dt: datetime) -> int:
    return int(dt.timestamp())


# ---------- ACCESS TOKEN (JWT signé) ----------
def create_access_token(
    sub: str, roles: Sequence[str], ttl_minutes: int | None = None
) -> str:
    """
    Crée un JWT HS256 de type 'access', court (par défaut ACCESS_TTL_MIN).
    Champs: sub (user_id UUID en str), roles, iat, exp, typ='access'
    """
    ttl = ttl_minutes or settings.ACCESS_TTL_MIN
    now = _now()
    exp = now + timedelta(minutes=ttl)
    payload = {
        "sub": str(sub),
        "roles": list(roles),
        "iat": _ts(now),
        "exp": _ts(exp),
        "typ": "access",
    }
    return jwt.encode(payload, settings.JWT_SECRET, algorithm=ALGO)


def verify_access_token(token: str) -> dict:
    """
    Décode/valide le JWT d'accès. Lève:
      - jwt.ExpiredSignatureError si expiré
      - jwt.InvalidTokenError si signature invalide / typ pas 'access'
    """
    payload = jwt.decode(token, settings.JWT_SECRET, algorithms=[ALGO])
    if payload.get("typ") != "access":
        raise jwt.InvalidTokenError("Wrong token type")
    return payload


# ---------- REFRESH TOKEN (opaque, hashé en DB) ----------
def _hash_refresh(raw: str) -> str:
    # HMAC-SHA256 (avec pepper) -> protège contre rainbow tables si la DB leak
    return hmac.new(
        settings.REFRESH_TOKEN_PEPPER.encode("utf-8"),
        raw.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def create_refresh_token_raw() -> str:
    # Long, non devinable, URL-safe
    return secrets.token_urlsafe(64)


async def issue_refresh_token(
    session: AsyncSession,
    user_id,
    ttl_days: int | None = None,
    user_agent: str | None = None,
    ip: str | None = None,
    single_device: bool = False,
) -> Tuple[str, RefreshToken]:
    """
    Génère un refresh token *opaque* (raw) et persiste son hash en DB.
    - single_device=True : révoque les anciens tokens de l'utilisateur avant d'en créer un nouveau.
    Retourne (raw_token, RefreshTokenRow)
    """
    if single_device:
        # Révoque tous les refresh actifs de l'utilisateur
        await session.execute(
            update(RefreshToken)
            .where(RefreshToken.user_id == user_id, RefreshToken.revoked_at.is_(None))
            .values(revoked_at=_now())
        )
    raw = create_refresh_token_raw()
    ttl = ttl_days or settings.REFRESH_TTL_DAYS
    rt = RefreshToken(
        user_id=user_id,
        token_hash=_hash_refresh(raw),
        user_agent=user_agent,
        ip=ip,
        expires_at=_now() + timedelta(days=ttl),
    )
    session.add(rt)
    await session.commit()
    await session.refresh(rt)
    return raw, rt


async def verify_refresh_token(
    session: AsyncSession, user_id, raw_token: str
) -> RefreshToken:
    """
    Valide un refresh:
      - hash correspond en DB
      - appartenance à user_id
      - non révoqué + non expiré
    Lève ValueError("unknown"/"revoked"/"expired") sinon.
    """
    token_hash = _hash_refresh(raw_token)
    row = (
        await session.scalars(
            select(RefreshToken).where(
                RefreshToken.user_id == user_id, RefreshToken.token_hash == token_hash
            )
        )
    ).first()
    if not row:
        raise ValueError("unknown")
    if row.revoked_at is not None:
        raise ValueError("revoked")
    if row.expires_at <= _now():
        raise ValueError("expired")
    return row


async def revoke_refresh_token(session: AsyncSession, row: RefreshToken) -> None:
    if row.revoked_at is None:
        await session.execute(
            update(RefreshToken)
            .where(RefreshToken.id == row.id)
            .values(revoked_at=_now())
        )
        await session.commit()


async def revoke_all_user_refresh(session: AsyncSession, user_id) -> int:
    res = await session.execute(
        update(RefreshToken)
        .where(RefreshToken.user_id == user_id, RefreshToken.revoked_at.is_(None))
        .values(revoked_at=_now())
    )
    await session.commit()
    return res.rowcount
