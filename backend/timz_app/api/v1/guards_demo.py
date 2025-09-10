from fastapi import APIRouter, Depends

from timz_app.core.security import require_roles
from timz_app.models.user import User

router = APIRouter(prefix="/demo", tags=["guards-demo"])


@router.get("/pro-only")
async def pro_only(user: User = Depends(require_roles("pro"))):
    """Accessible uniquement aux utilisateurs ayant le rôle 'pro'."""
    return {"ok": True, "as": "pro", "user_id": str(user.id)}


@router.get("/admin-only")
async def admin_only(user: User = Depends(require_roles("admin"))):
    """Accessible uniquement aux administrateurs."""
    return {"ok": True, "as": "admin", "user_id": str(user.id)}
