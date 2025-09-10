# timz_app/services/user_service.py
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Iterable, Sequence

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from timz_app.models.role import Role
from timz_app.models.user import User
from timz_app.models.user_role import UserRole


def _extract_claims(claims: dict) -> tuple[str, str | None, bool]:
    """
    Firebase ID token claims:
      - 'user_id' (ou 'sub') : UID Firebase
      - 'email' (optionnel)
      - 'email_verified' (bool)
    """
    uid = claims.get("user_id") or claims.get("sub")
    if not uid:
        raise ValueError("Missing Firebase UID in token claims (user_id/sub).")
    email = claims.get("email")
    email_verified = bool(claims.get("email_verified", False))
    return uid, email, email_verified


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


# -------- SYNC version (Session) --------
def upsert_user_from_claims(
    session: Session,
    claims: dict,
    default_role_names: Sequence[str] = ("client",),
    extra_role_names: Sequence[str] = (),
) -> User:
    uid, email, email_verified = _extract_claims(claims)

    user = session.scalar(select(User).where(User.firebase_uid == uid))
    if user is None:
        user = User(
            firebase_uid=uid,
            email=email,
            email_verified=email_verified,
            last_login_at=_now_utc(),
        )
        session.add(user)
        session.flush()  # pour obtenir user.id

        # Assigner les rôles par défaut (+ extra si passé)
        wanted = tuple(set(default_role_names) | set(extra_role_names))
        if wanted:
            roles = session.scalars(select(Role).where(Role.name.in_(wanted))).all()
            for r in roles:
                session.execute(
                    pg_insert(UserRole)
                    .values(user_id=user.id, role_id=r.id)
                    .on_conflict_do_nothing(index_elements=["user_id", "role_id"])
                )
    else:
        # Resync email / email_verified / last_login
        changed = False
        if email and user.email != email:
            user.email = email
            changed = True
        if user.email_verified != email_verified:
            user.email_verified = email_verified
            changed = True
        user.last_login_at = _now_utc()
        if changed:
            session.add(user)

    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        # Cas rare: conflit d'email (autre compte avec même email).
        # Tu peux ici lever une 409 ou ignorer la maj email. On choisit d'ignorer silencieusement:
        pass

    return user


# -------- ASYNC version (AsyncSession) --------
async def upsert_user_from_claims_async(
    session: AsyncSession,
    claims: dict,
    default_role_names: Sequence[str] = ("client",),
    extra_role_names: Sequence[str] = (),
) -> User:
    uid, email, email_verified = _extract_claims(claims)

    result = await session.scalars(select(User).where(User.firebase_uid == uid))
    user = result.first()
    if user is None:
        user = User(
            firebase_uid=uid,
            email=email,
            email_verified=email_verified,
            last_login_at=_now_utc(),
        )
        session.add(user)
        await session.flush()

        wanted = tuple(set(default_role_names) | set(extra_role_names))
        if wanted:
            roles = (
                await session.scalars(select(Role).where(Role.name.in_(wanted)))
            ).all()
            for r in roles:
                await session.execute(
                    pg_insert(UserRole)
                    .values(user_id=user.id, role_id=r.id)
                    .on_conflict_do_nothing(index_elements=["user_id", "role_id"])
                )
    else:
        changed = False
        if email and user.email != email:
            user.email = email
            changed = True
        if user.email_verified != email_verified:
            user.email_verified = email_verified
            changed = True
        user.last_login_at = _now_utc()
        if changed:
            session.add(user)

    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        # Voir commentaire sync: on ignore la maj email en cas de conflit.
        pass

    return user
