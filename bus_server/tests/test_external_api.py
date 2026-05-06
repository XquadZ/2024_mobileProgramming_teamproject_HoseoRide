"""Tests for external API calls — ITS CCTV, UTIC CCTV, Naver Directions.

All HTTP calls are mocked with httpx.MockTransport so no real network requests are made.
"""

import json
import os

import httpx
import pytest


def test_dedupe_nearby_cameras_prefers_streaming_its_camera():
    from scripts.fetch_cameras import _dedupe_nearby_cameras

    nearby = [
        {
            "camera_id": 156,
            "cum_dist": 756.8,
            "latitude": 36.7800207,
            "longitude": 127.0877001,
            "source": "utic",
            "stream_url": None,
        },
        {
            "camera_id": 51,
            "cum_dist": 756.8,
            "latitude": 36.7800207,
            "longitude": 127.0877001,
            "source": "its",
            "stream_url": "http://example.com/stream.m3u8",
        },
        {
            "camera_id": 270,
            "cum_dist": 1070.3,
            "latitude": 36.78706,
            "longitude": 127.10325,
            "source": "utic",
            "stream_url": "http://example.com/other.m3u8",
        },
    ]

    deduped = _dedupe_nearby_cameras(nearby)

    assert [cam["camera_id"] for cam in deduped] == [51, 270]


def test_dedupe_nearby_cameras_prefers_stream_url_before_source():
    from scripts.fetch_cameras import _dedupe_nearby_cameras

    nearby = [
        {
            "camera_id": 1,
            "cum_dist": 500.0,
            "latitude": 36.78,
            "longitude": 127.08,
            "source": "its",
            "stream_url": None,
        },
        {
            "camera_id": 2,
            "cum_dist": 500.0,
            "latitude": 36.78,
            "longitude": 127.08,
            "source": "utic",
            "stream_url": "http://example.com/utic.m3u8",
        },
    ]

    deduped = _dedupe_nearby_cameras(nearby)

    assert [cam["camera_id"] for cam in deduped] == [2]


# ---------------------------------------------------------------------------
# ITS CCTV snapshot (cctv_poller.fetch_its_snapshot)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_its_snapshot_success():
    from app.services.cctv_poller import fetch_its_snapshot

    mock_response = {
        "response": {
            "data": [
                {
                    "cctvId": "C001",
                    "cctvName": "천안아산역 부근",
                    "cctvurl": "http://example.com/stream/C001.m3u8",
                    "coordX": 127.054,
                    "coordY": 36.771,
                }
            ]
        }
    }

    async def _handler(request: httpx.Request) -> httpx.Response:
        assert "cctvId" in str(request.url)
        return httpx.Response(200, json=mock_response)

    async with httpx.AsyncClient(transport=httpx.MockTransport(_handler)) as client:
        result = await fetch_its_snapshot("C001", client=client)

    assert result is not None
    assert result == b"http://example.com/stream/C001.m3u8"


@pytest.mark.asyncio
async def test_its_snapshot_no_data():
    from app.services.cctv_poller import fetch_its_snapshot

    async def _handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"response": {"data": []}})

    async with httpx.AsyncClient(transport=httpx.MockTransport(_handler)) as client:
        result = await fetch_its_snapshot("C999", client=client)

    assert result is None


@pytest.mark.asyncio
async def test_its_snapshot_no_stream_url():
    from app.services.cctv_poller import fetch_its_snapshot

    mock_response = {
        "response": {
            "data": [{"cctvId": "C001", "cctvName": "test"}]
            # no cctvurl
        }
    }

    async def _handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=mock_response)

    async with httpx.AsyncClient(transport=httpx.MockTransport(_handler)) as client:
        result = await fetch_its_snapshot("C001", client=client)

    assert result is None


@pytest.mark.asyncio
async def test_its_snapshot_http_error():
    from app.services.cctv_poller import fetch_its_snapshot

    async def _handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="Internal Server Error")

    async with httpx.AsyncClient(transport=httpx.MockTransport(_handler)) as client:
        result = await fetch_its_snapshot("C001", client=client)

    assert result is None


# ---------------------------------------------------------------------------
# UTIC CCTV snapshot (cctv_poller.fetch_utic_snapshot)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_utic_snapshot_success():
    from app.services.cctv_poller import fetch_utic_snapshot

    fake_jpeg = b"\xff\xd8\xff\xe0FAKE_JPEG_DATA"

    async def _handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if "cctvOpenData.do" in url:
            return httpx.Response(200, json={"imgurl": "http://example.com/img.jpg"})
        elif "img.jpg" in url:
            return httpx.Response(200, content=fake_jpeg)
        return httpx.Response(404)

    async with httpx.AsyncClient(transport=httpx.MockTransport(_handler)) as client:
        result = await fetch_utic_snapshot("U001", client=client)

    assert result == fake_jpeg


@pytest.mark.asyncio
async def test_utic_snapshot_no_image_url():
    from app.services.cctv_poller import fetch_utic_snapshot

    async def _handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"response": {}})

    async with httpx.AsyncClient(transport=httpx.MockTransport(_handler)) as client:
        result = await fetch_utic_snapshot("U001", client=client)

    assert result is None


@pytest.mark.asyncio
async def test_utic_snapshot_401_error():
    from app.services.cctv_poller import fetch_utic_snapshot

    async def _handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, text="Unauthorized")

    async with httpx.AsyncClient(transport=httpx.MockTransport(_handler)) as client:
        result = await fetch_utic_snapshot("U001", client=client)

    assert result is None


# ---------------------------------------------------------------------------
# ITS camera list (fetch_cameras.fetch_its_cameras)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_fetch_its_cameras_success(monkeypatch):
    from scripts.fetch_cameras import fetch_its_cameras

    mock_response = {
        "response": {
            "data": [
                {
                    "cctvId": "ITS001",
                    "cctvName": "천안IC 부근",
                    "coordX": 127.03,
                    "coordY": 36.79,
                    "cctvurl": "http://example.com/its001.m3u8",
                },
                {
                    "cctvId": "ITS002",
                    "cctvName": "아산IC 부근",
                    "coordX": 127.07,
                    "coordY": 36.74,
                    "cctvurl": "http://example.com/its002.m3u8",
                },
            ]
        }
    }

    async def _mock_get(self, url, **kwargs):
        return httpx.Response(200, json=mock_response, request=httpx.Request("GET", url))

    monkeypatch.setattr(httpx.AsyncClient, "get", _mock_get)
    monkeypatch.setattr("app.config.settings.its_api_key", "test-key")

    cameras = await fetch_its_cameras()
    assert len(cameras) == 2
    assert cameras[0]["external_id"] == "ITS001"
    assert cameras[0]["source"] == "its"
    assert cameras[0]["latitude"] == 36.79
    assert cameras[0]["longitude"] == 127.03
    assert cameras[1]["external_id"] == "ITS002"


@pytest.mark.asyncio
async def test_fetch_its_cameras_no_key(monkeypatch):
    from scripts.fetch_cameras import fetch_its_cameras

    monkeypatch.setattr("app.config.settings.its_api_key", "")
    result = await fetch_its_cameras()
    assert result == []


# ---------------------------------------------------------------------------
# UTIC camera list (fetch_cameras.fetch_utic_cameras — HTML file parsing)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_fetch_utic_cameras_no_file(monkeypatch, tmp_path):
    from scripts.fetch_cameras import fetch_utic_cameras

    # Point to a non-existent file
    monkeypatch.setattr("scripts.fetch_cameras.os.path.exists", lambda p: False)
    result = await fetch_utic_cameras()
    assert result == []


@pytest.mark.asyncio
async def test_fetch_utic_cameras_from_html(monkeypatch, tmp_path):
    from scripts import fetch_cameras as fc

    html_content = """<html><body>
    <table>
    <tr><td><p>RN</p></td><td><p>CCTVID</p></td><td><p>CCTVNAME</p></td>
        <td><p>CENTERNAME</p></td><td><p>XCOORD</p></td><td><p>YCOORD</p></td></tr>
    <tr><td><p>1</p></td><td><p>E43001</p></td><td><p>갈산1교차로</p></td>
        <td><p>아산교통정보센터</p></td><td><p>127.065855</p></td><td><p>36.786463</p></td></tr>
    <tr><td><p>2</p></td><td><p>E43099</p></td><td><p>서울역</p></td>
        <td><p>서울교통정보센터</p></td><td><p>126.97</p></td><td><p>37.55</p></td></tr>
    </table></body></html>"""

    html_file = tmp_path / "OpenDataCCTV.html"
    html_file.write_text(html_content, encoding="utf-8")

    # Patch the file path resolution
    orig_join = os.path.join
    def _fake_join(*args):
        if "OpenDataCCTV.html" in args:
            return str(html_file)
        return orig_join(*args)

    monkeypatch.setattr("scripts.fetch_cameras.os.path.join", _fake_join)
    monkeypatch.setattr("scripts.fetch_cameras.os.path.exists", lambda p: True)

    # Mock the stream URL resolver to avoid real HTTP calls
    async def _noop_resolve(cameras):
        pass
    monkeypatch.setattr("scripts.fetch_cameras._resolve_utic_stream_urls", _noop_resolve)

    cameras = await fc.fetch_utic_cameras()
    # Only the camera within BBOX (127.065, 36.786) should be returned; Seoul is out of range
    assert len(cameras) == 1
    assert cameras[0]["external_id"] == "E43001"
    assert cameras[0]["name"] == "갈산1교차로"
    assert cameras[0]["source"] == "utic"
    assert cameras[0]["latitude"] == 36.786463
    assert cameras[0]["longitude"] == 127.065855


# ---------------------------------------------------------------------------
# UTIC stream URL resolution (_resolve_utic_stream_url_single)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_resolve_utic_stream_url_success(monkeypatch):
    import asyncio
    from scripts.fetch_cameras import _resolve_utic_stream_url_single

    monkeypatch.setattr("app.config.settings.utic_api_key", "testkey")

    cam_info_json = {
        "CCTVID": "L360002",
        "CCTVNAME": "개목삼거리",
        "KIND": "Z",
        "CCTVIP": "210.99.70.120",
        "CH": "",
        "ID": "cctv024",
        "PASSWD": "",
        "MOVIE": "Y",
    }
    jsp_html = '<video><source src="http://210.99.70.120:1935/live/cctv024.stream/playlist.m3u8" type="application/x-mpegURL"></video>'

    async def _handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if "getCctvInfoById.do" in url:
            return httpx.Response(200, json=cam_info_json)
        if "openDataCctvStream.jsp" in url:
            return httpx.Response(200, text=jsp_html)
        return httpx.Response(404)

    async with httpx.AsyncClient(transport=httpx.MockTransport(_handler)) as client:
        cam = {"external_id": "L360002", "stream_url": None}
        sem = asyncio.Semaphore(5)
        await _resolve_utic_stream_url_single(client, cam, "testkey", {}, sem)

    assert cam["stream_url"] == "http://210.99.70.120:1935/live/cctv024.stream/playlist.m3u8"


@pytest.mark.asyncio
async def test_resolve_utic_stream_url_movie_not_y(monkeypatch):
    import asyncio
    from scripts.fetch_cameras import _resolve_utic_stream_url_single

    async def _handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"CCTVID": "X001", "MOVIE": "N"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(_handler)) as client:
        cam = {"external_id": "X001", "stream_url": None}
        sem = asyncio.Semaphore(5)
        await _resolve_utic_stream_url_single(client, cam, "testkey", {}, sem)

    assert cam["stream_url"] is None


@pytest.mark.asyncio
async def test_resolve_utic_stream_url_api_error(monkeypatch):
    import asyncio
    from scripts.fetch_cameras import _resolve_utic_stream_url_single

    async def _handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"code": "9999", "msg": "비정상적인 접근입니다."})

    async with httpx.AsyncClient(transport=httpx.MockTransport(_handler)) as client:
        cam = {"external_id": "X002", "stream_url": None}
        sem = asyncio.Semaphore(5)
        await _resolve_utic_stream_url_single(client, cam, "testkey", {}, sem)

    assert cam["stream_url"] is None


# ---------------------------------------------------------------------------
# Naver Directions API (seed_data.fetch_naver_polyline)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_naver_polyline_success(monkeypatch):
    from scripts.seed_data import STOPS, fetch_naver_polyline

    mock_naver_response = {
        "route": {
            "traoptimal": [
                {
                    "path": [
                        [127.0755, 36.738],   # lng, lat (Naver format)
                        [127.068, 36.75],
                        [127.054, 36.771],
                        [127.002, 36.783],
                    ]
                }
            ]
        }
    }

    monkeypatch.setattr("app.config.settings.naver_client_id", "test_id")
    monkeypatch.setattr("app.config.settings.naver_client_secret", "test_secret")

    async def _mock_get(self, url, **kwargs):
        headers = kwargs.get("headers", {})
        assert headers["X-NCP-APIGW-API-KEY-ID"] == "test_id"
        assert headers["X-NCP-APIGW-API-KEY"] == "test_secret"
        return httpx.Response(200, json=mock_naver_response)

    monkeypatch.setattr(httpx.AsyncClient, "get", _mock_get)

    stops = ["아산캠퍼스", "천안아산역", "충무병원", "천안캠퍼스"]
    result = await fetch_naver_polyline(stops)

    assert result is not None
    assert len(result) == 4
    # Should be converted to [lat, lng]
    assert result[0] == [36.738, 127.0755]
    assert result[-1] == [36.783, 127.002]


@pytest.mark.asyncio
async def test_naver_polyline_no_key(monkeypatch):
    from scripts.seed_data import fetch_naver_polyline

    monkeypatch.setattr("app.config.settings.naver_client_id", "")
    monkeypatch.setattr("app.config.settings.naver_client_secret", "")

    result = await fetch_naver_polyline(["아산캠퍼스", "천안캠퍼스"])
    assert result is None


@pytest.mark.asyncio
async def test_naver_polyline_api_error(monkeypatch):
    from scripts.seed_data import fetch_naver_polyline

    monkeypatch.setattr("app.config.settings.naver_client_id", "test_id")
    monkeypatch.setattr("app.config.settings.naver_client_secret", "test_secret")

    async def _mock_get(self, url, **kwargs):
        return httpx.Response(403, text="Forbidden")

    monkeypatch.setattr(httpx.AsyncClient, "get", _mock_get)

    result = await fetch_naver_polyline(["아산캠퍼스", "천안캠퍼스"])
    assert result is None


@pytest.mark.asyncio
async def test_naver_polyline_empty_path(monkeypatch):
    from scripts.seed_data import fetch_naver_polyline

    monkeypatch.setattr("app.config.settings.naver_client_id", "test_id")
    monkeypatch.setattr("app.config.settings.naver_client_secret", "test_secret")

    async def _mock_get(self, url, **kwargs):
        return httpx.Response(200, json={"route": {"traoptimal": [{"path": []}]}})

    monkeypatch.setattr(httpx.AsyncClient, "get", _mock_get)

    result = await fetch_naver_polyline(["아산캠퍼스", "천안캠퍼스"])
    assert result is None
