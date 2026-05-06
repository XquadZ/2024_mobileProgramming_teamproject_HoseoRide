"""Hybrid stream manager — switches cameras between snapshot polling and live stream modes."""

import asyncio
import logging
from dataclasses import dataclass, field
from enum import Enum

logger = logging.getLogger(__name__)


class CameraMode(str, Enum):
    SNAPSHOT = "snapshot"
    STREAM = "stream"
    IDLE = "idle"


@dataclass
class CameraState:
    camera_id: int
    external_id: str
    source: str  # "utic" or "its"
    stream_url: str | None = None
    mode: CameraMode = CameraMode.IDLE
    route_id: int | None = None
    _stream_task: asyncio.Task | None = field(default=None, repr=False)


class StreamManager:
    """Controls per-camera modes and enforces the max concurrent stream limit."""

    def __init__(self, max_concurrent_streams: int = 3):
        self._cameras: dict[int, CameraState] = {}
        self._max_streams = max_concurrent_streams

    def register_camera(self, camera_id: int, external_id: str, source: str, stream_url: str | None = None):
        self._cameras[camera_id] = CameraState(
            camera_id=camera_id,
            external_id=external_id,
            source=source,
            stream_url=stream_url,
        )

    @property
    def active_stream_count(self) -> int:
        return sum(1 for c in self._cameras.values() if c.mode == CameraMode.STREAM)

    def activate_snapshot(self, camera_id: int, route_id: int | None = None):
        state = self._cameras.get(camera_id)
        if not state:
            return
        state.mode = CameraMode.SNAPSHOT
        state.route_id = route_id
        logger.info("Camera %d → SNAPSHOT mode (route=%s)", camera_id, route_id)

    def can_activate_stream(self) -> bool:
        return self.active_stream_count < self._max_streams

    def activate_stream(self, camera_id: int, route_id: int | None = None) -> bool:
        """Try to switch a camera to streaming mode. Returns False if at limit."""
        state = self._cameras.get(camera_id)
        if not state or not state.stream_url:
            return False
        if state.mode == CameraMode.STREAM:
            return True
        if not self.can_activate_stream():
            logger.warning(
                "Cannot activate stream for camera %d — at limit (%d/%d)",
                camera_id,
                self.active_stream_count,
                self._max_streams,
            )
            return False

        state.mode = CameraMode.STREAM
        state.route_id = route_id
        logger.info("Camera %d → STREAM mode (route=%s)", camera_id, route_id)
        return True

    def deactivate(self, camera_id: int):
        state = self._cameras.get(camera_id)
        if not state:
            return
        state.mode = CameraMode.IDLE
        state.route_id = None

    def get_snapshot_cameras(self) -> list[CameraState]:
        return [c for c in self._cameras.values() if c.mode == CameraMode.SNAPSHOT]

    def get_stream_cameras(self) -> list[CameraState]:
        return [c for c in self._cameras.values() if c.mode == CameraMode.STREAM]

    def get_state(self, camera_id: int) -> CameraState | None:
        return self._cameras.get(camera_id)


# Module-level singleton
stream_manager = StreamManager()
