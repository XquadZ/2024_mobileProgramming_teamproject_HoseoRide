"""CCTV real-time stream reader — decodes RTSP/HLS frames via PyAV."""

import asyncio
import logging
from collections.abc import AsyncGenerator

import av
import numpy as np

logger = logging.getLogger(__name__)
AVError = getattr(av, "AVError", av.FFmpegError)


def _next_frame(gen):
    try:
        return True, next(gen)
    except StopIteration:
        return False, None


async def read_stream_frames(
    stream_url: str,
    *,
    skip_frames: int = 2,
    max_frames: int = 300,
) -> AsyncGenerator[np.ndarray]:
    """Yield decoded video frames from an RTSP/HLS stream.

    Args:
        stream_url: RTSP or HLS URL.
        skip_frames: Process every N-th frame to reduce load.
        max_frames: Stop after this many yielded frames (safety limit).
    """
    loop = asyncio.get_running_loop()

    def _open_and_read():
        """Blocking generator that opens the stream and yields numpy frames."""
        try:
            container = av.open(stream_url, options={"rtsp_transport": "tcp"}, timeout=10)
        except AVError:
            logger.exception("Failed to open stream: %s", stream_url)
            return

        yielded = 0
        frame_idx = 0
        try:
            for frame in container.decode(video=0):
                if frame_idx % (skip_frames + 1) != 0:
                    frame_idx += 1
                    continue
                frame_idx += 1
                yield frame.to_ndarray(format="bgr24")
                yielded += 1
                if yielded >= max_frames:
                    break
        except AVError:
            logger.warning("Stream read error: %s", stream_url)
        finally:
            container.close()

    # Run the blocking generator in a thread and bridge to async
    gen = _open_and_read()
    while True:
        has_frame, frame = await loop.run_in_executor(None, _next_frame, gen)
        if not has_frame:
            break
        yield frame
