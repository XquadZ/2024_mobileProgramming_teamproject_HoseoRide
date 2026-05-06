"""Schedule-based shuttle route matching — infers whether a detected bus is a shuttle."""

import datetime
import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.route import RouteCameraMapping, ShuttleRoute
from app.models.schedule import Schedule
from app.models.sighting import Sighting

logger = logging.getLogger(__name__)


async def get_active_schedules(db: AsyncSession, now: datetime.datetime | None = None) -> list[dict]:
    """Return schedules that are currently active (within ±30 min of departure)."""
    if now is None:
        now = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=9)))

    current_time = now.strftime("%H:%M")
    day_map = {0: "weekday", 1: "weekday", 2: "weekday", 3: "weekday", 4: "friday", 5: "saturday", 6: "holiday"}
    day_type = day_map[now.weekday()]

    result = await db.execute(
        select(Schedule, ShuttleRoute)
        .join(ShuttleRoute, Schedule.route_id == ShuttleRoute.id)
        .where(Schedule.day_type == day_type, Schedule.is_active.is_(True))
    )

    active = []
    for schedule, route in result.all():
        dep_h, dep_m = map(int, schedule.departure_time.split(":"))
        dep_minutes = dep_h * 60 + dep_m
        cur_h, cur_m = map(int, current_time.split(":"))
        cur_minutes = cur_h * 60 + cur_m

        # Active window: from 5 min before departure to 60 min after
        if -5 <= (cur_minutes - dep_minutes) <= 60:
            active.append({
                "schedule_id": schedule.id,
                "route_id": route.id,
                "route_name": route.name,
                "departure_time": schedule.departure_time,
                "minutes_since_departure": cur_minutes - dep_minutes,
            })

    return active


async def get_route_cameras(db: AsyncSession, route_id: int) -> list[dict]:
    """Return cameras for a route in sequence order."""
    result = await db.execute(
        select(RouteCameraMapping)
        .where(RouteCameraMapping.route_id == route_id)
        .order_by(RouteCameraMapping.sequence_order)
    )
    return [
        {
            "camera_id": m.camera_id,
            "sequence_order": m.sequence_order,
            "expected_seconds_from_start": m.expected_seconds_from_start,
        }
        for m in result.scalars().all()
    ]


async def match_sighting_to_route(
    db: AsyncSession,
    camera_id: int,
    detected_at: datetime.datetime,
) -> dict | None:
    """Given a bus detection at a camera, try to match it to an active shuttle schedule.

    Returns the best-matching route/schedule info, or None if no match.
    """
    active_schedules = await get_active_schedules(db, detected_at)
    if not active_schedules:
        return None

    best_match = None
    best_score = 0.0

    for sched in active_schedules:
        route_cameras = await get_route_cameras(db, sched["route_id"])
        camera_in_route = next((c for c in route_cameras if c["camera_id"] == camera_id), None)
        if not camera_in_route:
            continue

        # Check timing consistency: does the elapsed time roughly match expected?
        expected_secs = camera_in_route["expected_seconds_from_start"]
        actual_secs = sched["minutes_since_departure"] * 60

        if expected_secs > 0:
            time_ratio = actual_secs / expected_secs
            # Allow 0.5x to 2.0x expected time (traffic variance)
            if not (0.5 <= time_ratio <= 2.0):
                continue
            timing_score = 1.0 - min(abs(time_ratio - 1.0), 1.0)
        else:
            timing_score = 0.5

        # Check sequential consistency: were buses seen at earlier cameras?
        earlier_cameras = [c for c in route_cameras if c["sequence_order"] < camera_in_route["sequence_order"]]
        if earlier_cameras:
            window_start = detected_at - datetime.timedelta(minutes=30)
            earlier_ids = [c["camera_id"] for c in earlier_cameras]
            result = await db.execute(
                select(Sighting)
                .where(
                    Sighting.camera_id.in_(earlier_ids),
                    Sighting.detected_at >= window_start,
                    Sighting.detected_at <= detected_at,
                )
            )
            prior_sightings = result.scalars().all()
            sequential_score = min(len(prior_sightings) / len(earlier_cameras), 1.0)
        else:
            sequential_score = 0.3  # First camera — less certain

        score = timing_score * 0.4 + sequential_score * 0.6

        if score > best_score:
            best_score = score
            trip_id = f"s{sched['schedule_id']}_d{sched['departure_time'].replace(':', '')}"
            best_match = {
                "route_id": sched["route_id"],
                "route_name": sched["route_name"],
                "schedule_id": sched["schedule_id"],
                "trip_id": trip_id,
                "confidence": score,
                "departure_time": sched["departure_time"],
            }

    return best_match
