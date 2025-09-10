# timz_app/api/v1/dev.py
from fastapi import APIRouter, Body, Depends, Header, HTTPException, status
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from timz_app.db.database import get_db
from timz_app.dependencies.firebase import verify_firebase_id_token_or_401
from timz_app.models.role import Role
from timz_app.models.user_role import UserRole
from timz_app.services.user_service import upsert_user_from_claims_async

router = APIRouter(prefix="/dev", tags=["dev"])
from sqlalchemy import text
from sqlalchemy.engine import make_url

from timz_app.core.config import settings


@router.get("/table-exists/{name}")
async def table_exists(name: str, db: AsyncSession = Depends(get_db)):
    """
    Return whether a table is visible in the current DB connection.
    Useful to confirm API's DB really has 'refresh_tokens'.
    """
    regclass = await db.scalar(text("SELECT to_regclass(:n)"), {"n": name})
    return {"table": name, "exists": regclass is not None, "regclass": regclass}


@router.get("/runtime-db-info")
async def runtime_db_info():
    """
    Show which DATABASE_URL the API actually loaded (sanitized).
    Helps catch 'Alembic DB != API DB' mismatches.
    """
    try:
        url = make_url(settings.DATABASE_URL)
        # sanitize
        return {
            "drivername": url.drivername,
            "username": url.username,
            "host": url.host,
            "port": url.port,
            "database": url.database,
        }
    except Exception as e:
        return {"error": str(e), "raw": settings.DATABASE_URL}


@router.get("/db-ping")
async def db_ping(db: AsyncSession = Depends(get_db)):
    """Simple DB liveness probe; returns {"db": "ok"} if the DB connection works."""
    await db.execute(text("SELECT 1"))
    return {"db": "ok"}


@router.get("/verify")
async def verify_only(
    authorization: str = Header(..., description="Bearer <FIREBASE_ID_TOKEN>"),
):
    """Verify a Firebase ID token and return a minimal view of its claims (uid/email)."""
    if not authorization.lower().startswith("bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing Bearer token"
        )
    id_token = authorization.split(" ", 1)[1].strip()
    claims = verify_firebase_id_token_or_401(id_token)
    return {
        "uid": claims.get("user_id") or claims.get("sub"),
        "email": claims.get("email"),
    }


@router.post("/upsert")
async def dev_upsert_from_firebase(
    authorization: str = Header(..., description="Bearer <FIREBASE_ID_TOKEN>"),
    db: AsyncSession = Depends(get_db),
    as_pro: bool = False,
):
    """
    Verify Firebase token, upsert user in DB (create on first visit), and ensure default 'client' role.
    Optional: pass ?as_pro=true to also add 'pro' for quick dev checks.
    """
    if not authorization.lower().startswith("bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing Bearer token"
        )
    id_token = authorization.split(" ", 1)[1].strip()
    claims = verify_firebase_id_token_or_401(id_token)

    extra = ("pro",) if as_pro else ()
    user = await upsert_user_from_claims_async(
        db, claims, default_role_names=("client",), extra_role_names=extra
    )

    result = await db.execute(
        select(Role.name)
        .join(UserRole, UserRole.role_id == Role.id)
        .where(UserRole.user_id == user.id)
        .order_by(Role.name)
    )
    role_names = result.scalars().all()

    return {
        "id": str(user.id),
        "firebase_uid": user.firebase_uid,
        "email": user.email,
        "email_verified": user.email_verified,
        "roles": role_names,
    }


@router.post("/peek-jwt")
async def peek_jwt(body: dict = Body(...)):
    """
    Return unverified header+payload of a JWT to inspect aud/iss/exp/email.
    Helpful to diagnose Invalid Firebase ID token.
    """
    import jwt

    token = (body.get("token") or "").strip()
    try:
        header = jwt.get_unverified_header(token)
        payload = jwt.decode(token, options={"verify_signature": False})
        return {"header": header, "payload": payload}
    except Exception as e:
        return {"error": f"{type(e).__name__}: {e}"}


@router.get("/settings-check")
async def settings_check():
    """Echo a couple of runtime settings to ensure the right environment is loaded."""
    from timz_app.core.config import settings

    return {
        "FIREBASE_PROJECT_ID": settings.FIREBASE_PROJECT_ID,
        "APP_ENV": settings.APP_ENV,
    }
