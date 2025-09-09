from fastapi import APIRouter, Depends

from app.core.security import get_current_user

router = APIRouter()


@router.get("/me")
async def me(user=Depends(get_current_user)):
    # user is a dict of Firebase claims (uid, email, etc.)
    return {"uid": user.get("uid"), "email": user.get("email")}
