"""Interactive viewer for mapped CCTV camera streams.

Usage:
    cd bus_server
    python -m scripts.debug_camera_stream --list
    python -m scripts.debug_camera_stream --route-id 3 --seq 2
    python -m scripts.debug_camera_stream --camera-id 51 --probe
"""

from __future__ import annotations

import argparse
import asyncio
import html
import sys
import time
from contextlib import suppress
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Condition, Thread

import cv2
from sqlalchemy import select

from app.core.database import async_session
from app.models.camera import Camera
from app.models.route import RouteCameraMapping, ShuttleRoute
from app.services.cctv_streamer import read_stream_frames


class DisplayUnavailableError(RuntimeError):
    """Raised when no local GUI backend is available for an OpenCV window."""


@dataclass(frozen=True)
class MappedCamera:
    route_id: int
    route_name: str
    sequence_order: int
    camera_id: int
    external_id: str
    source: str
    camera_name: str
    stream_url: str | None

    @property
    def has_stream(self) -> bool:
        return bool(self.stream_url)


class _FrameBuffer:
    def __init__(self) -> None:
        self._condition = Condition()
        self._frame_id = 0
        self._jpeg: bytes | None = None
        self._stopped = False

    def update(self, jpeg_bytes: bytes) -> None:
        with self._condition:
            self._frame_id += 1
            self._jpeg = jpeg_bytes
            self._condition.notify_all()

    def snapshot(self) -> bytes | None:
        with self._condition:
            return self._jpeg

    def wait_for_frame(self, last_seen: int, *, timeout: float = 5.0) -> tuple[int, bytes | None, bool]:
        with self._condition:
            if self._frame_id == last_seen and not self._stopped:
                self._condition.wait(timeout=timeout)
            return self._frame_id, self._jpeg, self._stopped

    def stop(self) -> None:
        with self._condition:
            self._stopped = True
            self._condition.notify_all()


async def load_mapped_cameras(route_id: int | None = None) -> list[MappedCamera]:
    stmt = (
        select(RouteCameraMapping, Camera, ShuttleRoute)
        .join(Camera, RouteCameraMapping.camera_id == Camera.id)
        .join(ShuttleRoute, RouteCameraMapping.route_id == ShuttleRoute.id)
        .order_by(ShuttleRoute.id, RouteCameraMapping.sequence_order, Camera.id)
    )
    if route_id is not None:
        stmt = stmt.where(RouteCameraMapping.route_id == route_id)

    async with async_session() as db:
        result = await db.execute(stmt)

    cameras: list[MappedCamera] = []
    for mapping, camera, route in result.all():
        cameras.append(
            MappedCamera(
                route_id=route.id,
                route_name=route.name,
                sequence_order=mapping.sequence_order,
                camera_id=camera.id,
                external_id=camera.external_id,
                source=camera.source,
                camera_name=camera.name,
                stream_url=camera.stream_url,
            )
        )
    return cameras


def resolve_camera(
    cameras: list[MappedCamera],
    *,
    camera_id: int | None = None,
    route_id: int | None = None,
    sequence_order: int | None = None,
) -> MappedCamera:
    matches = cameras
    if route_id is not None:
        matches = [camera for camera in matches if camera.route_id == route_id]
    if sequence_order is not None:
        matches = [camera for camera in matches if camera.sequence_order == sequence_order]
    if camera_id is not None:
        matches = [camera for camera in matches if camera.camera_id == camera_id]

    if not matches:
        raise ValueError("No mapped camera matches the requested selection.")
    if len(matches) > 1:
        raise ValueError("Selection is ambiguous. Add --route-id or --seq.")
    return matches[0]


def print_camera_list(cameras: list[MappedCamera]) -> None:
    if not cameras:
        print("No mapped cameras found.")
        return

    print("idx  route_id  route        seq  camera_id  src   stream  name")
    print("---  --------  -----------  ---  ---------  ----  ------  ----")
    for idx, camera in enumerate(cameras, start=1):
        print(
            f"{idx:>3}  "
            f"{camera.route_id:>8}  "
            f"{camera.route_name:<11}  "
            f"{camera.sequence_order:>3}  "
            f"{camera.camera_id:>9}  "
            f"{camera.source:<4}  "
            f"{'yes' if camera.has_stream else 'no':<6}  "
            f"{camera.camera_name}"
        )


def prompt_for_camera(cameras: list[MappedCamera]) -> MappedCamera:
    print_camera_list(cameras)
    if not cameras:
        raise ValueError("No mapped cameras available for selection.")

    while True:
        raw = input("Choose camera index (`q` to quit): ").strip()
        if raw.lower() in {"q", "quit", "exit"}:
            raise KeyboardInterrupt
        try:
            index = int(raw)
        except ValueError:
            print("Enter a valid numeric index.")
            continue
        if 1 <= index <= len(cameras):
            return cameras[index - 1]
        print(f"Index must be between 1 and {len(cameras)}.")


def _overlay_frame(frame, camera: MappedCamera) -> None:
    cv2.putText(
        frame,
        f"route={camera.route_id} seq={camera.sequence_order} cam={camera.camera_id} src={camera.source}",
        (16, 28),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.7,
        (0, 255, 0),
        2,
        cv2.LINE_AA,
    )
    cv2.putText(
        frame,
        f"ext={camera.external_id}  q/ESC=quit  s=save frame",
        (16, 58),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.65,
        (255, 255, 255),
        2,
        cv2.LINE_AA,
    )


def _save_frame(frame, camera: MappedCamera) -> Path:
    output_dir = Path("debug_captures")
    output_dir.mkdir(exist_ok=True)
    timestamp = time.strftime("%Y%m%d-%H%M%S")
    path = output_dir / f"route{camera.route_id}-seq{camera.sequence_order}-cam{camera.camera_id}-{timestamp}.jpg"
    cv2.imwrite(str(path), frame)
    return path


def _encode_jpeg(frame, *, quality: int) -> bytes:
    ok, encoded = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), quality])
    if not ok:
        raise RuntimeError("Failed to encode frame as JPEG.")
    return encoded.tobytes()


async def probe_stream(camera: MappedCamera, *, skip_frames: int) -> tuple[int, int, float]:
    if not camera.stream_url:
        raise RuntimeError("Selected camera has no stream_url.")

    started = time.perf_counter()
    async for frame in read_stream_frames(camera.stream_url, skip_frames=skip_frames, max_frames=1):
        elapsed = time.perf_counter() - started
        height, width = frame.shape[:2]
        return width, height, elapsed

    raise RuntimeError("No frame received from stream.")


def _create_window(window_name: str) -> None:
    try:
        cv2.namedWindow(window_name, cv2.WINDOW_NORMAL)
        cv2.resizeWindow(window_name, 1280, 720)
    except cv2.error as exc:
        raise DisplayUnavailableError(
            "OpenCV window display is unavailable in this environment. "
            "Use `--mode mjpeg` or run with a GUI backend."
        ) from exc


async def display_stream_in_window(
    camera: MappedCamera,
    *,
    skip_frames: int,
    reconnect_delay: float,
) -> None:
    if not camera.stream_url:
        raise RuntimeError("Selected camera has no stream_url.")

    window_name = f"Camera {camera.camera_id} - {camera.camera_name}"
    _create_window(window_name)

    try:
        while True:
            received_frame = False
            try:
                async for frame in read_stream_frames(
                    camera.stream_url,
                    skip_frames=skip_frames,
                    max_frames=1_000_000,
                ):
                    received_frame = True
                    display = frame.copy()
                    _overlay_frame(display, camera)
                    cv2.imshow(window_name, display)

                    key = cv2.waitKey(1) & 0xFF
                    if key in {27, ord("q")}:
                        return
                    if key == ord("s"):
                        saved = _save_frame(display, camera)
                        print(f"Saved frame to {saved}")

                    if cv2.getWindowProperty(window_name, cv2.WND_PROP_VISIBLE) < 1:
                        return
            except Exception as exc:
                print(f"Stream error: {exc}")

            message = "Stream ended" if received_frame else "No frame received"
            print(f"{message}; reconnecting in {reconnect_delay:.1f}s...")
            await asyncio.sleep(reconnect_delay)
    finally:
        with suppress(cv2.error):
            cv2.destroyAllWindows()


def _make_mjpeg_handler(frame_buffer: _FrameBuffer, camera: MappedCamera):
    class Handler(BaseHTTPRequestHandler):
        server_version = "BusTrackerDebug/1.0"

        def log_message(self, format: str, *args) -> None:
            return

        def do_GET(self) -> None:
            if self.path in {"/", "/index.html"}:
                self._serve_index()
                return
            if self.path == "/snapshot.jpg":
                self._serve_snapshot()
                return
            if self.path == "/stream.mjpg":
                self._serve_stream()
                return
            self.send_error(404, "Not found")

        def _serve_index(self) -> None:
            title = html.escape(f"{camera.route_name} seq={camera.sequence_order} cam={camera.camera_id}")
            name = html.escape(camera.camera_name)
            body = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{title}</title>
  <style>
    html, body {{ margin: 0; height: 100%; background: #111; color: #f5f5f5; font-family: sans-serif; }}
    body {{ display: flex; flex-direction: column; }}
    header {{ padding: 10px 14px; background: #1b1b1b; flex: 0 0 auto; }}
    .viewer {{ flex: 1 1 auto; min-height: 0; display: flex; align-items: center; justify-content: center; background: #000; }}
    img {{ display: block; width: 100%; height: 100%; object-fit: contain; }}
    small {{ color: #bbb; }}
  </style>
</head>
<body>
  <header>
    <div>{title}</div>
    <small>{name}</small>
  </header>
  <div class="viewer">
    <img src="/stream.mjpg" alt="camera stream">
  </div>
</body>
</html>
""".encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _serve_snapshot(self) -> None:
            jpeg = frame_buffer.snapshot()
            if not jpeg:
                self.send_error(503, "No frame available yet")
                return
            self.send_response(200)
            self.send_header("Content-Type", "image/jpeg")
            self.send_header("Content-Length", str(len(jpeg)))
            self.end_headers()
            self.wfile.write(jpeg)

        def _serve_stream(self) -> None:
            boundary = b"frame"
            self.send_response(200)
            self.send_header("Cache-Control", "no-store, no-cache, must-revalidate, max-age=0")
            self.send_header("Pragma", "no-cache")
            self.send_header("Connection", "close")
            self.send_header("Content-Type", "multipart/x-mixed-replace; boundary=frame")
            self.end_headers()

            last_seen = -1
            try:
                while True:
                    frame_id, jpeg, stopped = frame_buffer.wait_for_frame(last_seen)
                    if stopped:
                        break
                    if not jpeg or frame_id == last_seen:
                        continue
                    self.wfile.write(b"--" + boundary + b"\r\n")
                    self.wfile.write(b"Content-Type: image/jpeg\r\n")
                    self.wfile.write(f"Content-Length: {len(jpeg)}\r\n\r\n".encode("ascii"))
                    self.wfile.write(jpeg)
                    self.wfile.write(b"\r\n")
                    self.wfile.flush()
                    last_seen = frame_id
            except (BrokenPipeError, ConnectionResetError):
                return

    return Handler


async def display_stream_as_mjpeg(
    camera: MappedCamera,
    *,
    skip_frames: int,
    reconnect_delay: float,
    host: str,
    port: int,
    jpeg_quality: int,
    max_fps: float,
) -> None:
    if not camera.stream_url:
        raise RuntimeError("Selected camera has no stream_url.")

    frame_buffer = _FrameBuffer()
    handler = _make_mjpeg_handler(frame_buffer, camera)
    try:
        server = ThreadingHTTPServer((host, port), handler)
    except OSError as exc:
        raise RuntimeError(f"Failed to bind MJPEG server on {host}:{port}: {exc}") from exc

    server.daemon_threads = True
    server_thread = Thread(target=server.serve_forever, kwargs={"poll_interval": 0.2}, daemon=True)
    server_thread.start()

    print(f"MJPEG viewer ready: http://{host}:{port}")
    print("Open that URL in a browser. Press Ctrl+C to stop.")
    min_interval = (1.0 / max_fps) if max_fps > 0 else 0.0

    try:
        while True:
            received_frame = False
            last_push = 0.0
            try:
                async for frame in read_stream_frames(
                    camera.stream_url,
                    skip_frames=skip_frames,
                    max_frames=1_000_000,
                ):
                    received_frame = True
                    now = time.perf_counter()
                    if min_interval and now - last_push < min_interval:
                        continue
                    display = frame.copy()
                    _overlay_frame(display, camera)
                    frame_buffer.update(_encode_jpeg(display, quality=jpeg_quality))
                    last_push = now
            except Exception as exc:
                print(f"Stream error: {exc}")

            message = "Stream ended" if received_frame else "No frame received"
            print(f"{message}; reconnecting in {reconnect_delay:.1f}s...")
            await asyncio.sleep(reconnect_delay)
    finally:
        frame_buffer.stop()
        server.shutdown()
        server.server_close()
        server_thread.join(timeout=1.0)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Open a mapped CCTV stream for debugging.")
    parser.add_argument("--list", action="store_true", help="Print mapped cameras and exit.")
    parser.add_argument("--route-id", type=int, help="Filter to a specific route.")
    parser.add_argument("--seq", type=int, help="Pick a route sequence number. Requires --route-id.")
    parser.add_argument("--camera-id", type=int, help="Pick a specific camera_id.")
    parser.add_argument("--probe", action="store_true", help="Open the stream just long enough to fetch one frame.")
    parser.add_argument(
        "--mode",
        choices=("auto", "window", "mjpeg"),
        default="auto",
        help="Viewer mode. `auto` tries an OpenCV window first, then falls back to MJPEG.",
    )
    parser.add_argument("--host", default="127.0.0.1", help="Host for MJPEG mode. Default: 127.0.0.1")
    parser.add_argument("--port", type=int, default=8765, help="Port for MJPEG mode. Default: 8765")
    parser.add_argument("--mjpeg-quality", type=int, default=75, help="JPEG quality for MJPEG mode. Default: 75")
    parser.add_argument("--mjpeg-max-fps", type=float, default=8.0, help="Max FPS for MJPEG mode. Default: 8")
    parser.add_argument("--skip-frames", type=int, default=0, help="Process every N-th frame while viewing.")
    parser.add_argument("--reconnect-delay", type=float, default=1.0, help="Delay before reconnect after stream end.")
    return parser


async def async_main(args: argparse.Namespace) -> int:
    if args.seq is not None and args.route_id is None:
        raise ValueError("--seq requires --route-id.")

    cameras = await load_mapped_cameras(route_id=args.route_id)
    if args.list:
        print_camera_list(cameras)
        return 0
    if not cameras:
        print("No mapped cameras found.")
        return 1

    try:
        if args.camera_id is not None or args.seq is not None:
            camera = resolve_camera(
                cameras,
                camera_id=args.camera_id,
                route_id=args.route_id,
                sequence_order=args.seq,
            )
        else:
            camera = prompt_for_camera(cameras)
    except KeyboardInterrupt:
        print("Selection cancelled.")
        return 1

    print(
        f"Selected route={camera.route_name} seq={camera.sequence_order} "
        f"camera_id={camera.camera_id} source={camera.source}"
    )

    if args.probe:
        width, height, elapsed = await probe_stream(camera, skip_frames=args.skip_frames)
        print(f"Probe OK: {width}x{height} frame received in {elapsed:.2f}s")
        return 0

    if args.mode == "mjpeg":
        await display_stream_as_mjpeg(
            camera,
            skip_frames=args.skip_frames,
            reconnect_delay=args.reconnect_delay,
            host=args.host,
            port=args.port,
            jpeg_quality=args.mjpeg_quality,
            max_fps=args.mjpeg_max_fps,
        )
        return 0

    try:
        await display_stream_in_window(
            camera,
            skip_frames=args.skip_frames,
            reconnect_delay=args.reconnect_delay,
        )
    except DisplayUnavailableError as exc:
        if args.mode == "window":
            raise RuntimeError(str(exc)) from exc
        print(str(exc))
        print("Falling back to MJPEG browser viewer.")
        await display_stream_as_mjpeg(
            camera,
            skip_frames=args.skip_frames,
            reconnect_delay=args.reconnect_delay,
            host=args.host,
            port=args.port,
            jpeg_quality=args.mjpeg_quality,
            max_fps=args.mjpeg_max_fps,
        )
    return 0


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    try:
        return asyncio.run(async_main(args))
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print("\nStopped.")
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
