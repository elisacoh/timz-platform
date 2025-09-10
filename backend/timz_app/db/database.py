# backend/timz_app/db/database.py
from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from timz_app.core.config import settings

# ---- tests: utiliser NullPool pour éviter "another operation is in progress"
engine_kwargs = dict(echo=False, future=True)
if settings.APP_ENV == "test":
    from sqlalchemy.pool import NullPool

    engine_kwargs["poolclass"] = NullPool

# ⚠️ >> passer engine_kwargs ici <<
engine = create_async_engine(settings.DATABASE_URL, **engine_kwargs)

AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        yield session
