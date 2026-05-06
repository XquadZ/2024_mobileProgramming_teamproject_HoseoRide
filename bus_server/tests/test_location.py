"""Tests for /api/buses/location endpoints."""

import json
from unittest.mock import AsyncMock

import pytest


# ---------------------------------------------------------------------------
# GET /api/buses/location  (no buses tracked)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_get_all_locations_empty(client):
    resp = await client.get("/api/buses/location")
    assert resp.status_code == 200
    assert resp.json() == []


# ---------------------------------------------------------------------------
# GET /api/buses/location/{route_id}  (no buses tracked)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_get_route_locations_empty(client):
    resp = await client.get("/api/buses/location/1")
    assert resp.status_code == 200
    assert resp.json() == []


# ---------------------------------------------------------------------------
# GET /api/buses/location  (with mocked data)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_get_all_locations_with_data(client):
    import app.api.location as loc_mod

    bus_data = {
        "latitude": 36.75,
        "longitude": 127.06,
        "confidence": 0.85,
        "updated_at": "2026-03-12T10:00:00",
    }

    fake_redis = AsyncMock()
    fake_redis.get = AsyncMock(return_value=json.dumps(bus_data))

    async def _scan_iter(match="*"):
        yield "bus:location:1:trip_abc"
        yield "bus:location:2:trip_def"

    fake_redis.scan_iter = _scan_iter

    original = loc_mod.redis_client
    loc_mod.redis_client = fake_redis

    resp = await client.get("/api/buses/location")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 2
    assert data[0]["route_id"] == 1
    assert data[0]["trip_id"] == "trip_abc"
    assert data[0]["latitude"] == 36.75
    assert data[1]["route_id"] == 2

    loc_mod.redis_client = original


# ---------------------------------------------------------------------------
# GET /api/buses/location/{route_id}  (with mocked data)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_get_route_locations_with_data(client):
    import app.api.location as loc_mod

    bus_data = {
        "latitude": 36.783,
        "longitude": 127.002,
        "confidence": 0.92,
        "updated_at": "2026-03-12T10:05:00",
    }

    fake_redis = AsyncMock()
    fake_redis.get = AsyncMock(return_value=json.dumps(bus_data))

    async def _scan_iter(match="*"):
        yield "bus:location:1:trip_xyz"

    fake_redis.scan_iter = _scan_iter

    original = loc_mod.redis_client
    loc_mod.redis_client = fake_redis

    resp = await client.get("/api/buses/location/1")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["trip_id"] == "trip_xyz"
    assert data[0]["confidence"] == 0.92

    loc_mod.redis_client = original
