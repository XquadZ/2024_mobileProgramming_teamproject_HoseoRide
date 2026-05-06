"""Fetch CCTV cameras from UTIC/ITS APIs and auto-map them to shuttle routes.

Usage:
    cd bus_server
    python -m scripts.fetch_cameras                 # fetch + auto-map
    python -m scripts.fetch_cameras --radius 800    # custom radius in meters
"""

import asyncio
import json
import logging
import math
import os
import re
import sys
from html.parser import HTMLParser

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.config import settings
from app.models.base import Base
from app.models.camera import Camera
from app.models.route import RouteCameraMapping, ShuttleRoute

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

# 아산~천안 지역 bounding box (조회 범위)
BBOX = {
    "minX": "126.95",
    "maxX": "127.25",
    "minY": "36.70",
    "maxY": "36.87",
}


def _haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Distance in meters between two points."""
    R = 6_371_000
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlam = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlam / 2) ** 2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def _point_to_segment_distance(
    px: float, py: float,
    ax: float, ay: float,
    bx: float, by: float,
) -> float:
    """Approximate perpendicular distance (meters) from point P to line segment A-B."""
    abx, aby = bx - ax, by - ay
    apx, apy = px - ax, py - ay
    ab2 = abx * abx + aby * aby
    if ab2 == 0:
        return _haversine(px, py, ax, ay)
    t = max(0.0, min(1.0, (apx * abx + apy * aby) / ab2))
    proj_lat = ax + t * abx
    proj_lon = ay + t * aby
    return _haversine(px, py, proj_lat, proj_lon)


def _min_distance_to_polyline(lat: float, lon: float, waypoints: list[list[float]]) -> float:
    """Minimum distance from a point to a polyline (list of [lat, lng])."""
    min_dist = float("inf")
    for i in range(len(waypoints) - 1):
        d = _point_to_segment_distance(
            lat, lon,
            waypoints[i][0], waypoints[i][1],
            waypoints[i + 1][0], waypoints[i + 1][1],
        )
        min_dist = min(min_dist, d)
    return min_dist


def _project_on_polyline(lat: float, lon: float, waypoints: list[list[float]]) -> float:
    """Return cumulative distance (meters) along the polyline to the closest projection of the point."""
    best_cum = 0.0
    best_dist = float("inf")
    cum = 0.0

    for i in range(len(waypoints) - 1):
        seg_len = _haversine(waypoints[i][0], waypoints[i][1], waypoints[i + 1][0], waypoints[i + 1][1])
        d = _point_to_segment_distance(
            lat, lon,
            waypoints[i][0], waypoints[i][1],
            waypoints[i + 1][0], waypoints[i + 1][1],
        )
        if d < best_dist:
            best_dist = d
            # approximate projection fraction
            abx = waypoints[i + 1][0] - waypoints[i][0]
            aby = waypoints[i + 1][1] - waypoints[i][1]
            apx = lat - waypoints[i][0]
            apy = lon - waypoints[i][1]
            ab2 = abx * abx + aby * aby
            t = max(0.0, min(1.0, (apx * abx + apy * aby) / ab2)) if ab2 > 0 else 0.0
            best_cum = cum + t * seg_len
        cum += seg_len

    return best_cum


def _camera_preference(camera: dict) -> tuple[int, int]:
    """Return a sortable preference key for overlapping cameras."""
    return (
        1 if camera.get("stream_url") else 0,
        1 if camera.get("source") == "its" else 0,
    )


def _dedupe_nearby_cameras(
    nearby: list[dict],
    *,
    dedupe_radius_m: float = 5.0,
) -> list[dict]:
    """Collapse overlapping cameras and keep the most useful source.

    UTIC and ITS sometimes publish the same physical camera under different IDs.
    When that happens, prefer a camera with a stream URL, then prefer ITS.
    """
    if not nearby:
        return []

    kept: list[dict] = []
    for candidate in sorted(nearby, key=lambda item: item["cum_dist"]):
        duplicate_idx = None
        for idx, existing in enumerate(kept):
            if abs(candidate["cum_dist"] - existing["cum_dist"]) > dedupe_radius_m:
                continue
            gap = _haversine(
                candidate["latitude"],
                candidate["longitude"],
                existing["latitude"],
                existing["longitude"],
            )
            if gap <= dedupe_radius_m:
                duplicate_idx = idx
                break

        if duplicate_idx is None:
            kept.append(candidate)
            continue

        if _camera_preference(candidate) > _camera_preference(kept[duplicate_idx]):
            kept[duplicate_idx] = candidate

    kept.sort(key=lambda item: item["cum_dist"])
    return kept


# ---------------------------------------------------------------------------
# CCTV API 호출
# ---------------------------------------------------------------------------
async def fetch_its_cameras() -> list[dict]:
    """Fetch cameras from ITS (국가교통정보센터) API."""
    if not settings.its_api_key:
        logger.warning("ITS API key not set — skipping")
        return []

    url = f"{settings.its_base_url}/cctvInfo"
    params = {
        "apiKey": settings.its_api_key,
        "type": "its",
        "cctvType": "1",
        "getType": "json",
        **BBOX,
    }

    async with httpx.AsyncClient(timeout=20.0) as client:
        resp = await client.get(url, params=params)
        resp.raise_for_status()
        data = resp.json()

    items = data.get("response", {}).get("data", [])
    cameras = []
    for item in items:
        # ITS API returns lowercase field names: coordx, coordy, cctvname, cctvurl
        lat = float(item.get("coordy") or item.get("coordY") or 0)
        lon = float(item.get("coordx") or item.get("coordX") or 0)
        name = item.get("cctvname") or item.get("cctvName") or ""
        ext_id = item.get("cctvId") or item.get("roadsectionid") or ""
        if not ext_id:
            ext_id = f"its_{lat}_{lon}"
        cameras.append({
            "external_id": str(ext_id),
            "source": "its",
            "name": name,
            "latitude": lat,
            "longitude": lon,
            "road_name": name,
            "stream_url": item.get("cctvurl"),
            "snapshot_url": None,
        })
    logger.info("ITS: fetched %d cameras in region", len(cameras))
    return cameras


async def fetch_utic_cameras() -> list[dict]:
    """Parse UTIC camera data from the local HTML file (OpenDataCCTV.html).

    UTIC provides camera lists as an HTML table rather than a JSON API.
    The file contains columns: RN, CCTVID, CCTVNAME, CENTERNAME, XCOORD, YCOORD.
    We filter cameras within the BBOX and return them.
    """
    html_path = os.path.join(os.path.dirname(__file__), "..", "OpenDataCCTV.html")
    if not os.path.exists(html_path):
        logger.warning("UTIC HTML file not found at %s — skipping", html_path)
        return []

    class _TableParser(HTMLParser):
        def __init__(self):
            super().__init__()
            self.rows: list[list[str]] = []
            self.current_row: list[str] = []
            self.in_td = False
            self.in_p = False
            self.cell_text = ""

        def handle_starttag(self, tag, attrs):
            if tag == "tr":
                self.current_row = []
            elif tag == "td":
                self.in_td = True
                self.cell_text = ""
            elif tag == "p" and self.in_td:
                self.in_p = True

        def handle_endtag(self, tag):
            if tag == "td":
                self.current_row.append(self.cell_text.strip())
                self.in_td = False
                self.in_p = False
            elif tag == "tr":
                if len(self.current_row) >= 6:
                    self.rows.append(self.current_row[:6])

        def handle_data(self, data):
            if self.in_p and self.in_td:
                self.cell_text += data

    parser = _TableParser()
    with open(html_path, "r", encoding="utf-8") as f:
        parser.feed(f.read())

    min_x, max_x = float(BBOX["minX"]), float(BBOX["maxX"])
    min_y, max_y = float(BBOX["minY"]), float(BBOX["maxY"])

    cameras = []
    for row in parser.rows[1:]:  # skip header
        try:
            lon = float(row[4])
            lat = float(row[5])
        except (ValueError, IndexError):
            continue
        if not (min_x <= lon <= max_x and min_y <= lat <= max_y):
            continue
        cameras.append({
            "external_id": row[1],
            "source": "utic",
            "name": row[2],
            "latitude": lat,
            "longitude": lon,
            "road_name": row[2],
            "stream_url": None,
            "snapshot_url": None,
        })

    logger.info("UTIC: parsed %d cameras in region from HTML file", len(cameras))

    # Resolve HLS stream URLs via UTIC internal APIs
    if cameras:
        await _resolve_utic_stream_urls(cameras)

    return cameras


async def _resolve_utic_stream_url_single(
    client: httpx.AsyncClient,
    cam: dict,
    api_key: str,
    headers: dict,
    sem: asyncio.Semaphore,
) -> None:
    """Resolve the HLS stream URL for a single UTIC camera.

    1. Call getCctvInfoById.do to get connection params (KIND, ID, CCTVIP, CH, etc.)
    2. Call openDataCctvStream.jsp with those params
    3. Extract the HLS URL from the <source> tag in the response
    """
    async with sem:
        cctvid = cam["external_id"]
        try:
            r = await client.get(
                "http://www.utic.go.kr/map/getCctvInfoById.do",
                params={"cctvId": cctvid},
                headers=headers,
            )
            r.raise_for_status()
            info = r.json()
        except Exception:
            logger.debug("getCctvInfoById failed for %s", cctvid)
            return

        if info.get("code") == "9999" or info.get("MOVIE") != "Y":
            return

        # Build the JSP URL with full connection params
        params = {
            "key": api_key,
            "cctvid": info.get("CCTVID", cctvid),
            "cctvName": info.get("CCTVNAME", ""),
            "kind": info.get("KIND", ""),
            "cctvip": info.get("CCTVIP") or "undefined",
            "cctvch": info.get("CH") or "undefined",
            "id": info.get("ID") or "undefined",
            "cctvpasswd": info.get("PASSWD") or "undefined",
            "cctvport": "undefined",
        }
        try:
            r2 = await client.get(
                "http://www.utic.go.kr/jsp/map/openDataCctvStream.jsp",
                params=params,
            )
            r2.raise_for_status()
        except Exception:
            logger.debug("openDataCctvStream.jsp failed for %s", cctvid)
            return

        match = re.search(r'<source[^>]+src=["\']([^"\']+\.m3u8[^"\']*)', r2.text)
        if match:
            cam["stream_url"] = match.group(1)
            logger.debug("Resolved stream URL for %s: %s", cctvid, cam["stream_url"])


async def _resolve_utic_stream_urls(cameras: list[dict]) -> None:
    """Resolve HLS stream URLs for all UTIC cameras in batch."""
    api_key = settings.utic_api_key
    if not api_key:
        logger.warning("UTIC API key not set — skipping stream URL resolution")
        return

    sem = asyncio.Semaphore(5)
    headers = {
        "Referer": "http://www.utic.go.kr/map/map.do",
        "X-Requested-With": "XMLHttpRequest",
    }

    async with httpx.AsyncClient(follow_redirects=True, timeout=15.0) as client:
        # Get session cookie
        await client.get("http://www.utic.go.kr/map/map.do")

        tasks = [
            _resolve_utic_stream_url_single(client, cam, api_key, headers, sem)
            for cam in cameras
        ]
        await asyncio.gather(*tasks, return_exceptions=True)

    resolved = sum(1 for c in cameras if c["stream_url"])
    logger.info("UTIC: resolved stream URLs for %d/%d cameras", resolved, len(cameras))


# ---------------------------------------------------------------------------
# DB 저장 + 경로 매핑
# ---------------------------------------------------------------------------
async def save_and_map(radius_m: float = 25.0) -> None:
    engine = create_async_engine(settings.database_url, echo=False)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # Fetch cameras from APIs (continue even if one source fails)
    its_cameras: list[dict] = []
    utic_cameras: list[dict] = []
    try:
        its_cameras = await fetch_its_cameras()
    except Exception:
        logger.exception("Failed to fetch ITS cameras — skipping")
    try:
        utic_cameras = await fetch_utic_cameras()
    except Exception:
        logger.exception("Failed to fetch UTIC cameras — skipping")
    all_raw = its_cameras + utic_cameras
    logger.info("Total cameras fetched: %d", len(all_raw))

    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        # Upsert cameras
        camera_id_map: dict[str, int] = {}
        for raw in all_raw:
            ext_id = raw["external_id"]
            existing = await session.execute(
                select(Camera).where(Camera.external_id == ext_id)
            )
            cam = existing.scalar_one_or_none()
            if cam is None:
                cam = Camera(**raw)
                session.add(cam)
                await session.flush()
            else:
                cam.stream_url = raw.get("stream_url") or cam.stream_url
                cam.snapshot_url = raw.get("snapshot_url") or cam.snapshot_url
            camera_id_map[ext_id] = cam.id

        await session.commit()

        result = await session.execute(select(Camera))
        all_cameras = result.scalars().all()
        logger.info("Cameras in DB: %d", len(all_cameras))

        # Load all routes
        result = await session.execute(select(ShuttleRoute))
        routes = result.scalars().all()

        if not routes:
            logger.error("No routes found. Run seed_data.py first!")
            await engine.dispose()
            return

        # Auto-map cameras to routes
        total_mappings = 0
        for route in routes:
            waypoints = json.loads(route.waypoints_json)
            if len(waypoints) < 2:
                continue

            # Total route length for expected_seconds estimation
            route_length = sum(
                _haversine(waypoints[i][0], waypoints[i][1], waypoints[i + 1][0], waypoints[i + 1][1])
                for i in range(len(waypoints) - 1)
            )
            # Assume 48 min total travel time (from timetable)
            total_time_sec = 48 * 60

            # Find cameras near this route
            nearby: list[dict] = []
            for cam in all_cameras:
                dist = _min_distance_to_polyline(cam.latitude, cam.longitude, waypoints)
                if dist <= radius_m:
                    cum_dist = _project_on_polyline(cam.latitude, cam.longitude, waypoints)
                    nearby.append({
                        "camera_id": cam.id,
                        "cum_dist": cum_dist,
                        "latitude": cam.latitude,
                        "longitude": cam.longitude,
                        "source": cam.source,
                        "stream_url": cam.stream_url,
                    })

            raw_count = len(nearby)
            nearby = _dedupe_nearby_cameras(nearby)

            # Clear old mappings for this route
            await session.execute(
                RouteCameraMapping.__table__.delete().where(
                    RouteCameraMapping.route_id == route.id
                )
            )

            for seq, candidate in enumerate(nearby, start=1):
                cam_id = candidate["camera_id"]
                cum_dist = candidate["cum_dist"]
                expected_sec = (cum_dist / route_length * total_time_sec) if route_length > 0 else 0
                session.add(
                    RouteCameraMapping(
                        route_id=route.id,
                        camera_id=cam_id,
                        sequence_order=seq,
                        expected_seconds_from_start=expected_sec,
                    )
                )
                total_mappings += 1

            logger.info(
                "Route '%s': %d cameras within %dm (%d overlapping removed)",
                route.name,
                len(nearby),
                int(radius_m),
                raw_count - len(nearby),
            )

        await session.commit()
        logger.info("Total route-camera mappings created: %d", total_mappings)

    await engine.dispose()
    logger.info("Camera fetch & mapping complete!")


if __name__ == "__main__":
    radius = 25.0
    for i, arg in enumerate(sys.argv):
        if arg == "--radius" and i + 1 < len(sys.argv):
            radius = float(sys.argv[i + 1])
    asyncio.run(save_and_map(radius_m=radius))
