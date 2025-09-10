import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from timz_app.db.database import AsyncSessionLocal


@pytest.mark.asyncio
async def test_db_connectivity():
    async with AsyncSessionLocal() as session:  # type: AsyncSession
        result = await session.execute(text("SELECT 1"))
        assert result.scalar() == 1
