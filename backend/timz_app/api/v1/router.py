from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from timz_app.api.v1 import admin as admin_api  # <-- add
from timz_app.api.v1 import auth, dev, guards_demo
from timz_app.db.database import get_db

api_router = APIRouter()
api_router.include_router(dev.router)
api_router.include_router(auth.router)
api_router.include_router(guards_demo.router)
api_router.include_router(admin_api.router)


@api_router.get("/ping")
async def ping():
    return {"pong": True}


@api_router.get("/db-ping")
async def db_ping(db: AsyncSession = Depends(get_db)):
    await db.execute(text("SELECT 1"))
    return {"db": "ok"}
