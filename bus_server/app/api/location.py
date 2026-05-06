"""Bus location REST endpoint — polling fallback for WebSocket."""

import json

from fastapi import APIRouter

from app.core.redis_client import redis_client

router = APIRouter(tags=["location"])


@router.get("/buses/location")
async def get_all_bus_locations():
    """Return current locations for all tracked buses."""
    keys = []
    async for key in redis_client.scan_iter(match="bus:location:*"):
        keys.append(key)

    locations = []
    for key in keys:
        raw = await redis_client.get(key)
        if raw:
            data = json.loads(raw)
            # key format: bus:location:{route_id}:{trip_id}
            parts = key.split(":")
            data["route_id"] = int(parts[2])
            data["trip_id"] = parts[3]
            locations.append(data)

    return locations


@router.get("/buses/location/{route_id}")
async def get_route_bus_locations(route_id: int):
    """Return current bus locations for a specific route."""
    keys = []
    async for key in redis_client.scan_iter(match=f"bus:location:{route_id}:*"):
        keys.append(key)

    locations = []
    for key in keys:
        raw = await redis_client.get(key)
        if raw:
            data = json.loads(raw)
            parts = key.split(":")
            data["trip_id"] = parts[3]
            locations.append(data)

    return locations
