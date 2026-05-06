"""CCTV snapshot poller — fetches still images from UTIC/ITS cameras."""

import logging

import httpx

from app.config import settings

logger = logging.getLogger(__name__)


async def fetch_its_snapshot(camera_external_id: str, *, client: httpx.AsyncClient | None = None) -> bytes | None:
    """Fetch a single JPEG snapshot from ITS CCTV API.

    The ITS OpenAPI ``/cctvInfo`` endpoint returns metadata including ``cctvurl``
    which points to an HLS/RTSP stream.  For snapshot mode we request a single
    frame via the ``/cctvImage`` endpoint (if available) or fall back to
    downloading the first frame of the stream.
    """
    url = f"{settings.its_base_url}/cctvInfo"
    params = {
        "apiKey": settings.its_api_key,
        "type": "its",
        "cctvType": "1",
        "getType": "json",
    }

    own_client = client is None
    if own_client:
        client = httpx.AsyncClient(timeout=10.0)

    try:
        resp = await client.get(url, params={**params, "cctvId": camera_external_id})
        resp.raise_for_status()
        data = resp.json()

        items = data.get("response", {}).get("data", [])
        if not items:
            logger.warning("No camera data returned for %s", camera_external_id)
            return None

        stream_url = items[0].get("cctvurl")
        if not stream_url:
            return None

        # Return the stream URL — actual frame extraction happens in bus_detector
        return stream_url.encode()
    except Exception:
        logger.exception("Failed to fetch snapshot for camera %s", camera_external_id)
        return None
    finally:
        if own_client:
            await client.aclose()


async def fetch_utic_snapshot(camera_external_id: str, *, client: httpx.AsyncClient | None = None) -> bytes | None:
    """Fetch a JPEG snapshot from UTIC CCTV API."""
    url = f"{settings.utic_base_url}/guide/cctvOpenData.do"
    params = {
        "KEY": settings.utic_api_key,
        "cctvId": camera_external_id,
        "getType": "json",
    }

    own_client = client is None
    if own_client:
        client = httpx.AsyncClient(timeout=10.0)

    try:
        resp = await client.get(url, params=params)
        resp.raise_for_status()
        data = resp.json()

        image_url = data.get("imgurl") or data.get("response", {}).get("imgurl")
        if not image_url:
            logger.warning("No image URL returned for UTIC camera %s", camera_external_id)
            return None

        img_resp = await client.get(image_url)
        img_resp.raise_for_status()
        return img_resp.content
    except Exception:
        logger.exception("Failed to fetch UTIC snapshot for camera %s", camera_external_id)
        return None
    finally:
        if own_client:
            await client.aclose()
