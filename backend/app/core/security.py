from __future__ import annotations

import base64
import json
import os
from functools import lru_cache
from typing import Any, Dict

import firebase_admin
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from firebase_admin import auth, credentials

from app.core.config import settings

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
