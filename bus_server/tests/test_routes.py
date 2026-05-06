"""Tests for /api/routes and /api/schedules endpoints."""

import pytest


# ---------------------------------------------------------------------------
# GET /api/routes
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_list_routes_empty(client):
    resp = await client.get("/api/routes")
    assert resp.status_code == 200
    assert resp.json() == []


@pytest.mark.asyncio
async def test_list_routes_seeded(seeded_client):
    resp = await seeded_client.get("/api/routes")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 2
    names = {r["name"] for r in data}
    assert "아산→천안" in names
    assert "천안→아산" in names

    route = data[0]
    assert "id" in route
    assert "campus" in route
    assert "direction" in route
    assert "color" in route
    assert "waypoints" in route
    assert isinstance(route["waypoints"], list)


# ---------------------------------------------------------------------------
# GET /api/routes/{route_id}
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_get_route_exists(seeded_client):
    # Get all routes first to find a valid ID
    routes = (await seeded_client.get("/api/routes")).json()
    route_id = routes[0]["id"]

    resp = await seeded_client.get(f"/api/routes/{route_id}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] == route_id
    assert data["name"] == routes[0]["name"]
    assert isinstance(data["waypoints"], list)
    assert len(data["waypoints"]) >= 2


@pytest.mark.asyncio
async def test_get_route_not_found(seeded_client):
    resp = await seeded_client.get("/api/routes/9999")
    assert resp.status_code == 200
    assert resp.json() == {"error": "Route not found"}


# ---------------------------------------------------------------------------
# GET /api/routes/{route_id}/schedules
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_get_route_schedules(seeded_client):
    routes = (await seeded_client.get("/api/routes")).json()
    asan_route = next(r for r in routes if r["name"] == "아산→천안")

    resp = await seeded_client.get(f"/api/routes/{asan_route['id']}/schedules")
    assert resp.status_code == 200
    data = resp.json()
    # seeded: 08:30 weekday, 09:00 weekday, 10:00 saturday
    assert len(data) == 3

    for s in data:
        assert "id" in s
        assert "departure_time" in s
        assert "day_type" in s

    # Should be sorted by departure_time
    times = [s["departure_time"] for s in data]
    assert times == sorted(times)


@pytest.mark.asyncio
async def test_get_route_schedules_empty(seeded_client):
    resp = await seeded_client.get("/api/routes/9999/schedules")
    assert resp.status_code == 200
    assert resp.json() == []


# ---------------------------------------------------------------------------
# GET /api/schedules?day_type=
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_list_schedules_weekday(seeded_client):
    resp = await seeded_client.get("/api/schedules", params={"day_type": "weekday"})
    assert resp.status_code == 200
    data = resp.json()
    # seeded: 3 weekday schedules (2 for 아산→천안 + 1 for 천안→아산)
    assert len(data) == 3
    for s in data:
        assert s["day_type"] == "weekday"
        assert "route_name" in s
        assert "departure_time" in s


@pytest.mark.asyncio
async def test_list_schedules_saturday(seeded_client):
    resp = await seeded_client.get("/api/schedules", params={"day_type": "saturday"})
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["day_type"] == "saturday"


@pytest.mark.asyncio
async def test_list_schedules_holiday(seeded_client):
    resp = await seeded_client.get("/api/schedules", params={"day_type": "holiday"})
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["day_type"] == "holiday"


@pytest.mark.asyncio
async def test_list_schedules_default_is_weekday(seeded_client):
    resp = await seeded_client.get("/api/schedules")
    assert resp.status_code == 200
    data = resp.json()
    for s in data:
        assert s["day_type"] == "weekday"
