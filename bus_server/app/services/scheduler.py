"""Hybrid scheduler — orchestrates snapshot polling, bus detection, and stream switching."""

import asyncio
import datetime
import logging

from sqlalchemy import select

from app.config import settings
from app.core.database import async_session
from app.models.camera import Camera
from app.models.route import RouteCameraMapping
from app.models.sighting import Sighting
from app.services.bus_detector import detect_buses, detect_buses_from_jpeg
from app.services.cctv_poller import fetch_its_snapshot, fetch_utic_snapshot
from app.services.cctv_streamer import read_stream_frames
from app.services.location_estimator import estimate_location, update_bus_location
from app.services.route_matcher import get_active_schedules, match_sighting_to_route
from app.services.stream_manager import stream_manager

logger = logging.getLogger(__name__)

_running = False
_task: asyncio.Task | None = None


async def _register_cameras():
    """Load all route-mapped cameras from DB and register them with the stream manager."""
    async with async_session() as db:
        result = await db.execute(
            select(Camera, RouteCameraMapping.route_id)
            .join(RouteCameraMapping, RouteCameraMapping.camera_id == Camera.id)
            .distinct(Camera.id)
        )
        for cam, route_id in result.all():
            stream_manager.register_camera(
                camera_id=cam.id,
                external_id=cam.external_id,
                source=cam.source,
                stream_url=cam.stream_url,
            )
            stream_manager.activate_snapshot(cam.id, route_id)

    snapshot_count = len(stream_manager.get_snapshot_cameras())
    logger.info("Registered %d cameras in SNAPSHOT mode", snapshot_count)


async def _fetch_snapshot(cam_state) -> bytes | None:
    """Fetch a JPEG snapshot from the appropriate API based on camera source."""
    if cam_state.source == "utic":
        return await fetch_utic_snapshot(cam_state.external_id)
    return await fetch_its_snapshot(cam_state.external_id)


async def _record_sighting(camera_id: int, route_match: dict, confidence: float):
    """Persist a bus sighting record to the database."""
    async with async_session() as db:
        sighting = Sighting(
            camera_id=camera_id,
            route_id=route_match.get("route_id"),
            confidence=confidence,
            trip_id=route_match.get("trip_id"),
            detected_at=datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=9))),
        )
        db.add(sighting)
        await db.commit()


async def _handle_detection(camera_id: int, detections: list[dict]):
    """Process bus detections: match to route, record sighting, update location."""
    if not detections:
        return

    best = max(detections, key=lambda d: d["confidence"])

    async with async_session() as db:
        now = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=9)))
        route_match = await match_sighting_to_route(db, camera_id, now)

    if not route_match:
        logger.debug("Bus detected at camera %d but no route match", camera_id)
        return

    await _record_sighting(camera_id, route_match, best["confidence"])

    # Estimate and publish location
    async with async_session() as db:
        loc = await estimate_location(
            db,
            route_id=route_match["route_id"],
            trip_id=route_match["trip_id"],
            last_camera_id=camera_id,
            detected_at=now,
        )

    await update_bus_location(
        route_id=route_match["route_id"],
        trip_id=route_match["trip_id"],
        lat=loc["latitude"],
        lng=loc["longitude"],
        confidence=loc["confidence"],
    )

    logger.info(
        "Bus tracked: route=%s trip=%s camera=%d conf=%.2f loc=(%.5f, %.5f)",
        route_match["route_name"],
        route_match["trip_id"],
        camera_id,
        best["confidence"],
        loc["latitude"],
        loc["longitude"],
    )

    # Activate stream on the next camera in the route sequence if possible
    await _activate_next_stream(camera_id, route_match)


async def _activate_next_stream(camera_id: int, route_match: dict):
    """Try to switch the next sequential camera on this route to STREAM mode."""
    async with async_session() as db:
        result = await db.execute(
            select(RouteCameraMapping)
            .where(RouteCameraMapping.route_id == route_match["route_id"])
            .order_by(RouteCameraMapping.sequence_order)
        )
        mappings = result.scalars().all()

    current_seq = None
    for m in mappings:
        if m.camera_id == camera_id:
            current_seq = m.sequence_order
            break

    if current_seq is None:
        return

    # Find the next camera in sequence
    for m in mappings:
        if m.sequence_order > current_seq:
            if stream_manager.activate_stream(m.camera_id, route_match["route_id"]):
                logger.info(
                    "Activated STREAM on next camera %d (seq %d) for route %s",
                    m.camera_id,
                    m.sequence_order,
                    route_match["route_name"],
                )
            break


async def _poll_snapshot_cameras():
    """One round of snapshot polling for all cameras in SNAPSHOT mode."""
    cameras = stream_manager.get_snapshot_cameras()
    if not cameras:
        return

    # Check if there are any active schedules before processing
    async with async_session() as db:
        active = await get_active_schedules(db)
    if not active:
        return

    for cam_state in cameras:
        try:
            # Both ITS and UTIC cameras use HLS streams.
            # In snapshot mode, grab a single frame from HLS for detection.
            if cam_state.stream_url:
                async for frame in read_stream_frames(cam_state.stream_url, skip_frames=0, max_frames=1):
                    detections = detect_buses(frame)
                    if detections:
                        await _handle_detection(cam_state.camera_id, detections)
                continue

            # Fallback: try legacy JPEG snapshot fetch
            data = await _fetch_snapshot(cam_state)
            if not data:
                continue
            detections = detect_buses_from_jpeg(data)
            if detections:
                await _handle_detection(cam_state.camera_id, detections)
        except Exception:
            logger.exception("Error polling camera %d", cam_state.camera_id)


async def _process_stream_camera(cam_state):
    """Read frames from a streaming camera and run detection on each."""
    if not cam_state.stream_url:
        stream_manager.deactivate(cam_state.camera_id)
        return

    consecutive_empty = 0
    max_empty = 10  # deactivate stream after N consecutive frames with no bus

    try:
        async for frame in read_stream_frames(cam_state.stream_url, skip_frames=2, max_frames=150):
            detections = detect_buses(frame)
            if detections:
                consecutive_empty = 0
                await _handle_detection(cam_state.camera_id, detections)
            else:
                consecutive_empty += 1
                if consecutive_empty >= max_empty:
                    logger.info(
                        "No bus in %d consecutive frames — deactivating stream on camera %d",
                        max_empty,
                        cam_state.camera_id,
                    )
                    break
    except Exception:
        logger.exception("Stream error on camera %d", cam_state.camera_id)
    finally:
        stream_manager.deactivate(cam_state.camera_id)
        # Return to snapshot mode
        stream_manager.activate_snapshot(cam_state.camera_id, cam_state.route_id)


async def _process_stream_cameras():
    """Launch stream processing tasks for all cameras currently in STREAM mode."""
    cameras = stream_manager.get_stream_cameras()
    if not cameras:
        return

    tasks = [asyncio.create_task(_process_stream_camera(cam)) for cam in cameras]
    await asyncio.gather(*tasks, return_exceptions=True)


async def _scheduler_loop():
    """Main scheduler loop — alternates between snapshot polling and stream processing."""
    global _running

    logger.info("Hybrid scheduler started (interval=%ds)", settings.snapshot_interval_seconds)

    await _register_cameras()

    while _running:
        try:
            # 1. Poll snapshot cameras
            await _poll_snapshot_cameras()

            # 2. Process any active stream cameras (non-blocking, runs concurrently)
            stream_cameras = stream_manager.get_stream_cameras()
            if stream_cameras:
                asyncio.create_task(_process_stream_cameras())

            # 3. Wait for next polling interval
            await asyncio.sleep(settings.snapshot_interval_seconds)

        except asyncio.CancelledError:
            logger.info("Scheduler cancelled")
            break
        except Exception:
            logger.exception("Scheduler loop error")
            await asyncio.sleep(settings.snapshot_interval_seconds)

    logger.info("Hybrid scheduler stopped")


async def start_scheduler():
    """Start the scheduler as a background asyncio task."""
    global _running, _task
    if _running:
        return

    _running = True
    _task = asyncio.create_task(_scheduler_loop())
    logger.info("Scheduler task created")


async def stop_scheduler():
    """Stop the scheduler gracefully."""
    global _running, _task
    _running = False
    if _task:
        _task.cancel()
        try:
            await _task
        except asyncio.CancelledError:
            pass
        _task = None
    logger.info("Scheduler task stopped")
