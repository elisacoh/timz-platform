# tests/conftest.py
import os
from pathlib import Path

import pytest
from asgi_lifespan import LifespanManager
from httpx import ASGITransport, AsyncClient
from sqlalchemy import make_url, text


# -----------------------
# 1) ENV test (session)
# -----------------------
@pytest.fixture(scope="session", autouse=True)
def set_test_env():
    """
    Configure l'env de test au niveau session, SANS le fixture monkeypatch.
    On utilise pytest.MonkeyPatch manuellement (compatible session scope).
    """
    mp = pytest.MonkeyPatch()
    mp.setenv("APP_ENV", "test")
    mp.setenv(
        "DATABASE_URL",
        os.getenv(
            "TEST_DATABASE_URL",
            "postgresql+asyncpg://postgres:postgres@127.0.0.1:5435/timz_test",
        ),
    )
    mp.setenv("JWT_SECRET", "testsecret")
    mp.setenv("REFRESH_TOKEN_PEPPER", "superpepper")
    mp.setenv("ACCESS_TTL_MIN", "1")
    mp.setenv("REFRESH_TTL_DAYS", "1")
    mp.setenv("FIREBASE_PROJECT_ID", "timz-platform")

    # Recharge settings à partir de l'env
    import timz_app.core.config as cfg

    cfg.settings = cfg.Settings()

    yield cfg.settings
    mp.undo()


def _to_sync_url(url: str) -> str:
    # Alembic doit parler en sync
    return url.replace("+asyncpg", "+psycopg")


def _ensure_database_exists(sync_url: str):
    """
    Se connecte à 'postgres' et crée la base cible si manquante.
    """
    from psycopg import connect

    url = make_url(sync_url)
    admin_url = url.set(database="postgres")
    with connect(str(admin_url)) as conn:
        conn.autocommit = True
        with conn.cursor() as cur:
            cur.execute("SELECT 1 FROM pg_database WHERE datname=%s", (url.database,))
            if cur.fetchone() is None:
                cur.execute(f'CREATE DATABASE "{url.database}"')


# -----------------------
# 2) Migrations Alembic
# -----------------------
@pytest.fixture(scope="session", autouse=True)
def run_migrations(set_test_env):
    """
    Lance les migrations sur l'URL *synchrone* (psycopg) pour éviter MissingGreenlet.
    """
    from alembic import command
    from alembic.config import Config

    import timz_app.core.config as cfg

    cfgfile = Config()
    script_location = str(
        Path(__file__).resolve().parents[1] / "timz_app" / "db" / "migrations"
    )
    cfgfile.set_main_option("script_location", script_location)
    cfgfile.set_main_option("sqlalchemy.url", _to_sync_url(cfg.settings.DATABASE_URL))

    command.upgrade(cfgfile, "head")
    yield
    # pas de downgrade ici


# -----------------------
# 3) Client HTTP async
# -----------------------


@pytest.fixture
async def client():
    # import tardif => settings déjà patchés par set_test_env
    from timz_app.main import app

    async with LifespanManager(app):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            yield ac


# -----------------------
# 4) DB cleanup + seed
# -----------------------
@pytest.fixture(autouse=True)
async def db_clean_seed():
    """
    Truncate tables entre les tests + seed des rôles.
    """
    from timz_app.db.database import AsyncSessionLocal

    async with AsyncSessionLocal() as s:
        await s.execute(
            text(
                "TRUNCATE TABLE refresh_tokens, user_roles, users RESTART IDENTITY CASCADE;"
            )
        )
        await s.execute(
            text(
                """
            INSERT INTO roles (name) VALUES ('client'), ('pro'), ('admin')
            ON CONFLICT (name) DO NOTHING;
        """
            )
        )
        await s.commit()
    yield


# -----------------------
# 5) Mock Firebase
# -----------------------
@pytest.fixture(autouse=True)
def mock_firebase_verifier(monkeypatch):
    """
    Replace Firebase verifier everywhere it's used.
    Patch BOTH the provider module and the service module import.
    """

    def _fake_verify(id_token: str):
        return {
            "user_id": "testuid",
            "sub": "testuid",
            "email": "test@mail.com",
            "email_verified": False,
        }

    import timz_app.dependencies.firebase as fb
    import timz_app.services.auth_service as asvc

    # Patch the original function on the provider module
    monkeypatch.setattr(
        fb, "verify_firebase_id_token_or_401", _fake_verify, raising=True
    )
    # Patch the imported reference inside the service module
    monkeypatch.setattr(
        asvc, "verify_firebase_id_token_or_401", _fake_verify, raising=True
    )
