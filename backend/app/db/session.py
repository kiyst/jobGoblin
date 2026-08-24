import asyncio
from collections.abc import AsyncGenerator
from functools import lru_cache

from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.config import Settings, get_settings


@lru_cache
def get_engine() -> AsyncEngine:
    settings = get_settings()
    return create_async_engine(
        settings.database_url,
        pool_pre_ping=True,
        connect_args={"timeout": settings.database_connect_timeout_seconds},
    )


def get_sessionmaker() -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(get_engine(), expire_on_commit=False)


async def get_session() -> AsyncGenerator[AsyncSession]:
    """FastAPI dependency yielding a request-scoped async session.

    Not used by any Phase 0 route — `/health` never touches the database, and
    `/ready` opens its own short-lived connection directly (see
    `app/api/health.py`) rather than depending on this, so a connectivity
    check isn't tangled up with ORM session lifecycle. This exists now so
    Phase 1's routers/services have a ready-made dependency to import.
    """
    sessionmaker = get_sessionmaker()
    async with sessionmaker() as session:
        yield session


async def check_database_connection(settings: Settings) -> None:
    """Run a minimal query to prove the database is reachable.

    Raises on failure — callers (currently only `/ready`) decide how to
    translate that into an HTTP response. Uses its own short-lived engine
    rather than the shared `get_engine()` singleton so a bad `database_url`
    override in tests doesn't get cached across test cases.
    """
    engine = create_async_engine(
        settings.database_url,
        connect_args={"timeout": settings.database_connect_timeout_seconds},
    )
    try:
        # asyncpg's own `timeout` covers the connection attempt itself, but a
        # stalled DNS lookup can fall outside that window — wrap the whole
        # thing so /ready has a hard upper bound on how long it can hang.
        async def _ping() -> None:
            async with engine.connect() as conn:
                await conn.execute(text("SELECT 1"))

        await asyncio.wait_for(_ping(), timeout=settings.database_connect_timeout_seconds + 1)
    finally:
        await engine.dispose()
