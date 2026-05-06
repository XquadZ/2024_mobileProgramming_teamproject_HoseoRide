"""Shuttle route & schedule REST endpoints."""

import json

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.route import ShuttleRoute
from app.models.schedule import Schedule

router = APIRouter(tags=["routes"])


@router.get("/routes")
async def list_routes(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(ShuttleRoute))
    routes = result.scalars().all()
    return [
        {
            "id": r.id,
            "name": r.name,
            "campus": r.campus,
            "direction": r.direction,
            "color": r.color,
            "waypoints": json.loads(r.waypoints_json),
        }
        for r in routes
    ]


@router.get("/routes/{route_id}")
async def get_route(route_id: int, db: AsyncSession = Depends(get_db)):
    route = await db.get(ShuttleRoute, route_id)
    if not route:
        return {"error": "Route not found"}
    return {
        "id": route.id,
        "name": route.name,
        "campus": route.campus,
        "direction": route.direction,
        "color": route.color,
        "waypoints": json.loads(route.waypoints_json),
    }


@router.get("/routes/{route_id}/schedules")
async def get_route_schedules(route_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Schedule)
        .where(Schedule.route_id == route_id, Schedule.is_active.is_(True))
        .order_by(Schedule.departure_time)
    )
    schedules = result.scalars().all()
    return [
        {
            "id": s.id,
            "departure_time": s.departure_time,
            "day_type": s.day_type,
        }
        for s in schedules
    ]


@router.get("/schedules")
async def list_all_schedules(day_type: str = "weekday", db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Schedule, ShuttleRoute)
        .join(ShuttleRoute, Schedule.route_id == ShuttleRoute.id)
        .where(Schedule.day_type == day_type, Schedule.is_active.is_(True))
        .order_by(Schedule.departure_time)
    )
    return [
        {
            "id": s.id,
            "route_id": r.id,
            "route_name": r.name,
            "departure_time": s.departure_time,
            "day_type": s.day_type,
        }
        for s, r in result.all()
    ]
