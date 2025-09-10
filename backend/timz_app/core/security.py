from __future__ import annotations

import base64
import json
import os
from functools import lru_cache
from typing import Any, Dict, Set

import firebase_admin
import jwt
from fastapi import Depends, Header, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from firebase_admin import auth, credentials
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from timz_app.core.config import settings
from timz_app.core.jwt import verify_access_token
from timz_app.db.database import get_db
from timz_app.models.role import Role
from timz_app.models.user import User
from timz_app.models.user_role import UserRole

http_bearer = HTTPBearer(auto_error=False)


def _init_firebase_from_settings() -> None:
    if firebase_admin._apps:
        return

    # Prefer explicit path
    if settings.GOOGLE_APPLICATION_CREDENTIALS and os.path.exists(
        settings.GOOGLE_APPLICATION_CREDENTIALS
    ):
        cred = credentials.Certificate(settings.GOOGLE_APPLICATION_CREDENTIALS)
        firebase_admin.initialize_app(cred)
        return

    # Else try base64
    if settings.FIREBASE_CREDENTIALS_B64:
        data = json.loads(
            base64.b64decode(settings.FIREBASE_CREDENTIALS_B64).decode("utf-8")
        )
        cred = credentials.Certificate(data)
        firebase_admin.initialize_app(cred)
        return

    # Fallback: Application Default Credentials (gcloud / env)
    try:
        cred = credentials.ApplicationDefault()
        firebase_admin.initialize_app(cred)
    except Exception as e:
        raise RuntimeError(
            "Firebase credentials not configured. Set GOOGLE_APPLICATION_CREDENTIALS "
            "or FIREBASE_CREDENTIALS_B64 in your .env."
        ) from e


@lru_cache(maxsize=1)
def _ensure_firebase_initialized() -> bool:
    _init_firebase_from_settings()
    return True


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(http_bearer),
) -> Dict[str, Any]:
    # Require Authorization: Bearer <idToken>
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authorization header missing",
        )

    _ensure_firebase_initialized()
    token = credentials.credentials
    try:
        decoded = auth.verify_id_token(token)
        return decoded  # dict with uid, email, etc.
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
        )


def _extract_bearer(authorization: str | None) -> str:
    """Extract raw token from 'Authorization: Bearer <token>' header."""
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing Bearer token"
        )
    return authorization.split(" ", 1)[1].strip()


async def get_current_user_db(
    authorization: str | None = Header(None),
    db: AsyncSession = Depends(get_db),
) -> User:
    """
    Validate the access JWT from Authorization header and load the user from DB.
    Raises 401 if token is missing/invalid/expired or user not found.
    """
    token = _extract_bearer(authorization)
    try:
        payload = verify_access_token(token)
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="access_token_expired"
        )
    except jwt.InvalidTokenError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="access_token_invalid"
        )

    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="access_token_missing_sub"
        )

    user = (await db.scalars(select(User).where(User.id == user_id))).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="user_not_found"
        )

    return user


async def fetch_user_role_names(db: AsyncSession, user_id) -> Set[str]:
    """
    Load user's role names from DB. We trust DB over JWT so role changes
    take effect immediately without attendre l'expiration d'un access token.
    """
    res = await db.execute(
        select(Role.name)
        .join(UserRole, UserRole.role_id == Role.id)
        .where(UserRole.user_id == user_id)
    )
    return set(res.scalars().all())


def require_roles(*required: str):
    """
    Dependency factory: ensures the current user has ALL required roles.
    Usage: user: User = Depends(require_roles("pro")), etc.
    """
    required_set = {r.strip().lower() for r in required if r}

    async def _dep(
        request: Request,
        user: User = Depends(get_current_user_db),
        db: AsyncSession = Depends(get_db),
    ) -> User:
        # --- per-request cache ---
        have = getattr(request.state, "role_names", None)
        if have is None:
            have = await fetch_user_role_names(db, user.id)
            request.state.role_names = have

        missing = [r for r in required_set if r not in have]
        if missing:
            raise HTTPException(
                status_code=403, detail=f"missing_roles:{','.join(missing)}"
            )
        return user

    return _dep
