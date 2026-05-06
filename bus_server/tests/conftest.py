"""Shared fixtures for API tests.

Uses an in-memory SQLite database and fakeredis so tests run without
external services (PostgreSQL / Redis).
"""

import asyncio
import json
from collections.abc import AsyncGenerator
from unittest.mock import AsyncMock, MagicMock

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.models.base import Base
from app.models.route import ShuttleRoute
from app.models.schedule import Schedule

# ---------------------------------------------------------------------------
# DB — async SQLite in-memory
# ---------------------------------------------------------------------------
TEST_DB_URL = "sqlite+aiosqlite:///:memory:"

engine = create_async_engine(TEST_DB_URL, echo=False)
TestSession = async_sessionmaker(engine, expire_on_commit=False)


async def _override_get_db() -> AsyncGenerator[AsyncSession]:
    async with TestSession() as session:
        yield session


# ---------------------------------------------------------------------------
# Redis — stub
# ---------------------------------------------------------------------------
def _make_fake_redis():
    """Return a minimal mock that satisfies the location endpoints."""
    r = AsyncMock()
    r.get = AsyncMock(return_value=None)

    async def _scan_iter(match: str = "*"):
        """Yield nothing — no buses tracked during tests."""
        return
        yield  # make it an async generator

    r.scan_iter = _scan_iter
    r.pubsub = MagicMock()
    return r


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------
@pytest_asyncio.fixture()
async def client():
    """Yield an httpx AsyncClient wired to the test app."""
    # Import here so module-level app init doesn't fail on missing Postgres.
    from app.core.database import get_db
    from app.main import app

    # Override dependencies
    app.dependency_overrides[get_db] = _override_get_db

    # Patch redis globally
    import app.api.location as loc_mod
    import app.core.redis_client as rc_mod

    fake_redis = _make_fake_redis()
    original_redis = rc_mod.redis_client
    rc_mod.redis_client = fake_redis
    loc_mod.redis_client = fake_redis

    # Create tables
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    transport = ASGITransport(app=app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

    # Cleanup
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    app.dependency_overrides.clear()
    rc_mod.redis_client = original_redis
    loc_mod.redis_client = original_redis


@pytest_asyncio.fixture()
async def seeded_client(client: AsyncClient):
    """Client with pre-seeded route + schedule data."""
    async with TestSession() as session:
        route1 = ShuttleRoute(
            name="아산→천안",
            campus="asan",
            direction="outbound",
            waypoints_json=json.dumps([[36.738, 127.0755], [36.783, 127.002]]),
            color="#1976D2",
        )
        route2 = ShuttleRoute(
            name="천안→아산",
            campus="cheonan",
            direction="outbound",
            waypoints_json=json.dumps([[36.783, 127.002], [36.738, 127.0755]]),
            color="#D32F2F",
        )
        session.add_all([route1, route2])
        await session.flush()

        schedules = [
            Schedule(route_id=route1.id, departure_time="08:30", day_type="weekday"),
            Schedule(route_id=route1.id, departure_time="09:00", day_type="weekday"),
            Schedule(route_id=route1.id, departure_time="10:00", day_type="saturday"),
            Schedule(route_id=route2.id, departure_time="08:30", day_type="weekday"),
            Schedule(route_id=route2.id, departure_time="14:00", day_type="holiday"),
        ]
        session.add_all(schedules)
        await session.commit()

    yield client
