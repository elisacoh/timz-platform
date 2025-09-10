import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select, text

from timz_app.core import config as cfg
from timz_app.db.database import AsyncSessionLocal
from timz_app.main import app
from timz_app.models.role import Role
from timz_app.models.user import User
from timz_app.models.user_role import UserRole


@pytest.mark.asyncio
async def test_auth_me_requires_bearer(client):
    r = await client.get("/api/v1/auth/me")
    assert r.status_code == 401
    assert r.json()["detail"] == "Missing Bearer token"


async def _get_user_by_email(email: str):
    async with AsyncSessionLocal() as s:
        return (await s.scalars(select(User).where(User.email == email))).first()


async def _grant_role(user_id, role_name: str):
    async with AsyncSessionLocal() as s:
        r = (await s.scalars(select(Role).where(Role.name == role_name))).first()
        s.add(UserRole(user_id=user_id, role_id=r.id))
        await s.commit()


@pytest.mark.asyncio
async def test_exchange_creates_user_and_returns_tokens(client: AsyncClient):
    # Call /auth/exchange with mocked Firebase id token
    resp = await client.post("/api/v1/auth/exchange", json={"id_token": "whatever"})
    assert resp.status_code == 200, resp.text
    data = resp.json()

    # tokens present
    assert "access_token" in data
    assert "refresh_token" in data
    assert data["user"]["email"] == "test@mail.com"
    assert "client" in data["user"]["roles"]

    # user persisted
    u = await _get_user_by_email("test@mail.com")
    assert u is not None


@pytest.mark.asyncio
async def test_access_me_works_with_access_token(client: AsyncClient):
    ex = (await client.post("/api/v1/auth/exchange", json={"id_token": "x"})).json()
    access = ex["access_token"]
    r = await client.get(
        "/api/v1/auth/me", headers={"Authorization": f"Bearer {access}"}
    )
    assert r.status_code == 200, r.text
    assert r.json()["email"] == "test@mail.com"


@pytest.mark.asyncio
async def test_access_me_rejects_tampered_token(client: AsyncClient):
    ex = (await client.post("/api/v1/auth/exchange", json={"id_token": "x"})).json()
    access = ex["access_token"]
    # Tamper: flip one char
    tampered = access[:-1] + ("A" if access[-1] != "A" else "B")
    r = await client.get(
        "/api/v1/auth/me", headers={"Authorization": f"Bearer {tampered}"}
    )
    assert r.status_code in (401, 403)  # 401 attendu selon ton implémentation
    # optional: check error message
    # assert "Invalid" in r.text or "expired" in r.text


@pytest.mark.asyncio
async def test_refresh_valid_and_rotation(client: AsyncClient):
    ex = (await client.post("/api/v1/auth/exchange", json={"id_token": "x"})).json()
    refresh = ex["refresh_token"]

    r1 = await client.post(
        "/api/v1/auth/refresh?rotate=true", json={"refresh_token": refresh}
    )
    assert r1.status_code == 200, r1.text
    d1 = r1.json()
    assert "access_token" in d1
    assert "refresh_token" in d1  # rotation returns a new refresh

    # old refresh must now be revoked
    r_old = await client.post(
        "/api/v1/auth/refresh?rotate=true", json={"refresh_token": refresh}
    )
    assert r_old.status_code == 401, r_old.text
    assert "revoked" in r_old.text or "unknown" in r_old.text


@pytest.mark.asyncio
async def test_refresh_unknown_token(client: AsyncClient):
    r = await client.post(
        "/api/v1/auth/refresh", json={"refresh_token": "not-a-real-token"}
    )
    assert r.status_code == 401
    assert "unknown" in r.text or "refresh" in r.text


@pytest.mark.asyncio
async def test_guards_forbid_without_role_then_pass_after_grant(client: AsyncClient):
    ex = (await client.post("/api/v1/auth/exchange", json={"id_token": "x"})).json()
    access = ex["access_token"]
    user_id = ex["user"]["id"]

    # No 'pro' yet -> 403
    r_forbid = await client.get(
        "/api/v1/demo/pro-only", headers={"Authorization": f"Bearer {access}"}
    )
    assert r_forbid.status_code == 403, r_forbid.text

    # Grant 'pro' in DB directly
    await _grant_role(user_id, "pro")

    # Same access token, but guard checks DB -> now 200
    r_ok = await client.get(
        "/api/v1/demo/pro-only", headers={"Authorization": f"Bearer {access}"}
    )
    assert r_ok.status_code == 200, r_ok.text
