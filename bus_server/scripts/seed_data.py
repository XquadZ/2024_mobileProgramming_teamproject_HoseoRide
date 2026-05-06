"""Seed script — populates shuttle routes, stops, and schedules from Hoseo University data.

Usage:
    cd bus_server
    python -m scripts.seed_data          # straight-line waypoints (no API key needed)
    python -m scripts.seed_data --naver  # fetch real driving polyline via Naver Directions API
"""

import asyncio
import json
import logging
import sys

import httpx
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.config import settings
from app.models.base import Base
from app.models.route import RouteCameraMapping, ShuttleRoute
from app.models.schedule import Schedule

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 정류장 좌표 (station.txt 기반 실제 좌표)
# ---------------------------------------------------------------------------
STOPS = {
    "아산캠퍼스": (36.7384244, 127.0768957),
    "천안아산역": (36.7934753, 127.1040128),
    "쌍용2동": (36.8009835, 127.1195278),
    "충무병원": (36.7982674, 127.1337418),
    "천안역": (36.8086925, 127.1494572),
    "천안터미널": (36.818755, 127.1565935),
    "천안캠퍼스": (36.8285962, 127.1836043),
}

# ---------------------------------------------------------------------------
# 노선 정의
# ---------------------------------------------------------------------------
ROUTES = [
    {
        "name": "아산→천안",
        "campus": "asan",
        "direction": "outbound",
        "color": "#1976D2",
        "stops": [
            "아산캠퍼스",
            "천안아산역",
            "쌍용2동",
            "충무병원",
            "천안역",
            "천안터미널",
            "천안캠퍼스",
        ],
        # 첫 정류장부터 각 정류장까지 예상 소요시간(초)
        # 아산→천안 총 약 48분(2880초), 정류장 간 균등 배분
        "expected_seconds": [0, 480, 960, 1440, 1920, 2400, 2880],
    },
    {
        "name": "천안→아산",
        "campus": "cheonan",
        "direction": "outbound",
        "color": "#D32F2F",
        "stops": [
            "천안캠퍼스",
            "천안터미널",
            "천안역",
            "충무병원",
            "쌍용2동",
            "천안아산역",
            "아산캠퍼스",
        ],
        "expected_seconds": [0, 480, 960, 1440, 1920, 2400, 2880],
    },
]

# ---------------------------------------------------------------------------
# 시간표 데이터 (호서대 웹사이트 2026학년도)
# ---------------------------------------------------------------------------

# 천안↔아산 월~목 (쌍방향 동시 출발)
_WEEKDAY_MON_THU = [
    "07:45", "08:30", "08:35", "08:40", "08:45", "08:50", "08:55", "09:00",
    "09:05", "09:10", "09:20", "09:30", "09:40", "09:50", "10:00", "10:10",
    "10:20", "10:35", "10:50", "11:05", "11:20", "11:50", "12:20", "12:50",
    "13:20", "13:40", "14:00", "14:20", "14:40", "15:00", "15:15", "15:20",
    "15:30", "15:45", "16:00", "16:15", "16:25", "16:35", "16:45", "16:55",
    "17:05", "17:15", "17:45", "18:00", "18:30", "19:00", "19:30", "20:00",
    "20:30", "21:00", "21:30",
]

# 금요일
_WEEKDAY_FRI = [
    "07:45", "08:40", "08:50", "09:00", "09:10", "09:20", "09:30", "09:40",
    "10:00", "10:20", "10:40", "11:00", "11:30", "12:00", "12:30", "13:00",
    "13:20", "13:40", "14:00", "14:20", "14:40", "15:00", "15:20", "15:40",
    "16:00", "16:20", "16:40", "17:00", "17:20", "17:45", "18:00", "18:20",
    "18:40", "19:00", "19:30", "20:00", "20:30", "21:00", "21:30",
]

# 토요일
_SATURDAY = [
    "09:00", "10:00", "11:30", "13:00", "14:30", "16:00", "17:30", "19:00",
]

# 일요일/공휴일 — 아산→천안
_HOLIDAY_ASAN_TO_CHEONAN = [
    "10:00", "12:00", "13:00", "14:00", "15:00", "16:00", "17:00", "18:00",
    "19:00", "20:00", "21:00",
]

# 일요일/공휴일 — 천안→아산
_HOLIDAY_CHEONAN_TO_ASAN = [
    "10:00", "12:00", "13:00", "14:00", "15:00", "16:00", "17:00", "18:00",
    "19:00", "20:00", "21:00",
]


def _build_schedules() -> list[dict]:
    """Build schedule records from timetable data."""
    schedules: list[dict] = []

    # route_name → (day_type, departure_times)
    pairs: list[tuple[str, str, list[str]]] = [
        # 월~목: 양방향 동시 출발
        ("아산→천안", "weekday", _WEEKDAY_MON_THU),
        ("천안→아산", "weekday", _WEEKDAY_MON_THU),
        # 금요일
        ("아산→천안", "friday", _WEEKDAY_FRI),
        ("천안→아산", "friday", _WEEKDAY_FRI),
        # 토요일
        ("아산→천안", "saturday", _SATURDAY),
        ("천안→아산", "saturday", _SATURDAY),
        # 일요일/공휴일
        ("아산→천안", "holiday", _HOLIDAY_ASAN_TO_CHEONAN),
        ("천안→아산", "holiday", _HOLIDAY_CHEONAN_TO_ASAN),
    ]

    for route_name, day_type, times in pairs:
        for t in times:
            schedules.append(
                {"route_name": route_name, "day_type": day_type, "departure_time": t}
            )
    return schedules


# ---------------------------------------------------------------------------
# Naver Directions API — optional polyline fetch
# ---------------------------------------------------------------------------
async def fetch_naver_polyline(stops: list[str]) -> list[list[float]] | None:
    """Fetch driving route polyline from Naver Directions 5 API.

    Returns list of [lat, lng] waypoints, or None on failure.
    """
    if not settings.naver_client_id or not settings.naver_client_secret:
        logger.warning("Naver API key not set — skipping polyline fetch")
        return None

    coords = [STOPS[s] for s in stops]
    start = f"{coords[0][1]},{coords[0][0]}"  # lng,lat
    goal = f"{coords[-1][1]},{coords[-1][0]}"
    waypoints = "|".join(f"{c[1]},{c[0]}" for c in coords[1:-1])

    url = "https://naveropenapi.apigw.ntruss.com/map-direction/v1/driving"
    params = {"start": start, "goal": goal}
    if waypoints:
        params["waypoints"] = waypoints

    headers = {
        "X-NCP-APIGW-API-KEY-ID": settings.naver_client_id,
        "X-NCP-APIGW-API-KEY": settings.naver_client_secret,
    }

    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.get(url, params=params, headers=headers)
        if resp.status_code != 200:
            logger.error("Naver Directions API error %d: %s", resp.status_code, resp.text[:200])
            return None
        data = resp.json()

    route = data.get("route", {}).get("traoptimal", [{}])[0]
    path = route.get("path", [])
    if not path:
        logger.error("No path returned from Naver Directions API")
        return None

    # Naver returns [lng, lat] — convert to [lat, lng]
    return [[p[1], p[0]] for p in path]


def _straight_line_waypoints(stops: list[str]) -> list[list[float]]:
    """Generate simple straight-line waypoints from stop coordinates."""
    return [[STOPS[s][0], STOPS[s][1]] for s in stops]


# ---------------------------------------------------------------------------
# Main seed logic
# ---------------------------------------------------------------------------
async def seed(use_naver: bool = False) -> None:
    engine = create_async_engine(settings.database_url, echo=False)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        # Clear existing data
        await session.execute(delete(Schedule))
        await session.execute(delete(RouteCameraMapping))
        await session.execute(delete(ShuttleRoute))
        await session.commit()

        route_id_map: dict[str, int] = {}

        # --- Insert routes ---
        for route_def in ROUTES:
            stops = route_def["stops"]

            if use_naver:
                waypoints = await fetch_naver_polyline(stops)
                if waypoints is None:
                    waypoints = _straight_line_waypoints(stops)
            else:
                waypoints = _straight_line_waypoints(stops)

            route = ShuttleRoute(
                name=route_def["name"],
                campus=route_def["campus"],
                direction=route_def["direction"],
                waypoints_json=json.dumps(waypoints),
                color=route_def["color"],
            )
            session.add(route)
            await session.flush()  # get auto ID
            route_id_map[route_def["name"]] = route.id
            logger.info("Route '%s' created (id=%d, %d waypoints)", route.name, route.id, len(waypoints))

        # --- Insert schedules ---
        schedule_data = _build_schedules()
        count = 0
        for s in schedule_data:
            route_id = route_id_map.get(s["route_name"])
            if route_id is None:
                continue
            session.add(
                Schedule(
                    route_id=route_id,
                    departure_time=s["departure_time"],
                    day_type=s["day_type"],
                )
            )
            count += 1

        await session.commit()
        logger.info("Inserted %d schedule records", count)

    await engine.dispose()
    logger.info("Seed complete!")


if __name__ == "__main__":
    use_naver = "--naver" in sys.argv
    asyncio.run(seed(use_naver))
