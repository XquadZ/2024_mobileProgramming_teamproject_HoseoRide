"""Location estimator — interpolates bus position along a route polyline."""

import datetime
import json
import logging
import math

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.redis_client import redis_client
from app.models.route import ShuttleRoute
from app.models.camera import Camera

logger = logging.getLogger(__name__)


def _haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Distance in meters between two lat/lng points."""
    R = 6_371_000
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlam = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlam / 2) ** 2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def _interpolate_on_polyline(
    waypoints: list[list[float]],
    distance_meters: float,
) -> tuple[float, float]:
    """Walk along a polyline (list of [lat, lng]) by a given distance and return the position."""
    remaining = distance_meters
    for i in range(len(waypoints) - 1):
        seg_dist = _haversine(
            waypoints[i][0], waypoints[i][1],
            waypoints[i + 1][0], waypoints[i + 1][1],
        )
        if remaining <= seg_dist:
            ratio = remaining / seg_dist if seg_dist > 0 else 0
            lat = waypoints[i][0] + ratio * (waypoints[i + 1][0] - waypoints[i][0])
            lng = waypoints[i][1] + ratio * (waypoints[i + 1][1] - waypoints[i][1])
            return lat, lng
        remaining -= seg_dist

    # Past the end — return last point
    return waypoints[-1][0], waypoints[-1][1]


async def estimate_location(
    db: AsyncSession,
    route_id: int,
    trip_id: str,
    last_camera_id: int,
    detected_at: datetime.datetime,
) -> dict:
    """Estimate current bus location based on last detection and average speed.

    The estimate interpolates along the route polyline from the camera position.
    """
    now = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=9)))
    elapsed_secs = (now - detected_at).total_seconds()
    speed_mps = settings.default_bus_speed_kmh * 1000 / 3600
    travel_distance = elapsed_secs * speed_mps

    # Get camera position
    cam = await db.get(Camera, last_camera_id)
    if not cam:
        return {"latitude": 0, "longitude": 0, "confidence": 0, "source": "unknown"}

    # Get route waypoints
    route = await db.get(ShuttleRoute, route_id)
    if not route:
        return {"latitude": cam.latitude, "longitude": cam.longitude, "confidence": 0.3, "source": "camera"}

    waypoints = json.loads(route.waypoints_json)

    # Find the camera's position on the polyline
    cam_distance = 0.0
    min_dist_to_cam = float("inf")
    best_idx = 0
    for i, wp in enumerate(waypoints):
        d = _haversine(cam.latitude, cam.longitude, wp[0], wp[1])
        if d < min_dist_to_cam:
            min_dist_to_cam = d
            best_idx = i

    # Sum distances up to the closest waypoint
    for i in range(best_idx):
        cam_distance += _haversine(
            waypoints[i][0], waypoints[i][1],
            waypoints[i + 1][0], waypoints[i + 1][1],
        )

    # Interpolate from camera position along remaining route
    estimated_distance = cam_distance + travel_distance
    lat, lng = _interpolate_on_polyline(waypoints, estimated_distance)

    # Confidence decays with elapsed time (stale data = less confident)
    confidence = max(0.1, 1.0 - (elapsed_secs / 600))  # drops to 0.1 after 10 min

    return {
        "latitude": lat,
        "longitude": lng,
        "confidence": round(confidence, 3),
        "source": "interpolated",
        "elapsed_seconds": elapsed_secs,
    }


async def update_bus_location(
    route_id: int, trip_id: str, lat: float, lng: float, confidence: float
):
    """Push updated location to Redis for real-time serving."""
    key = f"bus:location:{route_id}:{trip_id}"
    data = json.dumps({
        "latitude": lat,
        "longitude": lng,
        "confidence": confidence,
        "updated_at": datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=9))).isoformat(),
    })
    await redis_client.set(key, data, ex=120)  # expires in 2 min if not refreshed
    await redis_client.publish(f"bus:updates:{route_id}", data)
