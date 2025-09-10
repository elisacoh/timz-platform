from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Path, status
from pydantic import BaseModel
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from timz_app.core.security import require_roles
from timz_app.db.database import get_db
from timz_app.models.role import Role
from timz_app.models.user import User
from timz_app.models.user_role import UserRole

router = APIRouter(prefix="/admin", tags=["admin"])


class RoleChangeResponse(BaseModel):
    """API response for grant/revoke operations."""

    user_id: UUID
    role: str
    operation: str  # "grant" | "revoke"
    changed: bool  # True if a DB change occurred (idempotent-safe)


@router.post(
    "/users/{user_id}/roles/{role}",
    response_model=RoleChangeResponse,
    summary="Grant a role to a user (admin only, idempotent)",
)
async def grant_role(
    user_id: UUID = Path(..., description="Target user's UUID"),
    role: str = Path(..., description="Role name (e.g., client | pro | admin)"),
    _admin: User = Depends(require_roles("admin")),
    db: AsyncSession = Depends(get_db),
):
    """
    Grant a role to a user. Idempotent: re-granting an existing role returns `changed=false`.
    404 if user or role doesn't exist.
    """
    role_name = role.strip().lower()

    user = (await db.scalars(select(User).where(User.id == user_id))).first()
    if not user:
        raise HTTPException(status_code=404, detail="user_not_found")

    role_row = (await db.scalars(select(Role).where(Role.name == role_name))).first()
    if not role_row:
        raise HTTPException(status_code=404, detail="role_not_found")

    link = (
        await db.scalars(
            select(UserRole).where(
                UserRole.user_id == user_id, UserRole.role_id == role_row.id
            )
        )
    ).first()

    if link:
        return RoleChangeResponse(
            user_id=user_id, role=role_name, operation="grant", changed=False
        )

    db.add(UserRole(user_id=user_id, role_id=role_row.id))
    await db.commit()
    return RoleChangeResponse(
        user_id=user_id, role=role_name, operation="grant", changed=True
    )


@router.delete(
    "/users/{user_id}/roles/{role}",
    response_model=RoleChangeResponse,
    summary="Revoke a role from a user (admin only, idempotent)",
)
async def revoke_role(
    user_id: UUID = Path(..., description="Target user's UUID"),
    role: str = Path(..., description="Role name (e.g., client | pro | admin)"),
    _admin: User = Depends(require_roles("admin")),
    db: AsyncSession = Depends(get_db),
):
    """
    Revoke a role from a user. Idempotent: revoking a missing role returns `changed=false`.
    404 if user or role doesn't exist.
    """
    role_name = role.strip().lower()

    user = (await db.scalars(select(User).where(User.id == user_id))).first()
    if not user:
        raise HTTPException(status_code=404, detail="user_not_found")

    role_row = (await db.scalars(select(Role).where(Role.name == role_name))).first()
    if not role_row:
        raise HTTPException(status_code=404, detail="role_not_found")

    res = await db.execute(
        delete(UserRole).where(
            UserRole.user_id == user_id, UserRole.role_id == role_row.id
        )
    )
    await db.commit()
    changed = (res.rowcount or 0) > 0
    return RoleChangeResponse(
        user_id=user_id, role=role_name, operation="revoke", changed=changed
    )
