from scripts.debug_camera_stream import MappedCamera, resolve_camera


def _camera(
    *,
    route_id: int,
    route_name: str,
    sequence_order: int,
    camera_id: int,
) -> MappedCamera:
    return MappedCamera(
        route_id=route_id,
        route_name=route_name,
        sequence_order=sequence_order,
        camera_id=camera_id,
        external_id=f"cam-{camera_id}",
        source="utic",
        camera_name=f"Camera {camera_id}",
        stream_url="http://example.com/stream.m3u8",
    )


def test_resolve_camera_by_route_and_sequence():
    cameras = [
        _camera(route_id=3, route_name="아산→천안", sequence_order=1, camera_id=261),
        _camera(route_id=3, route_name="아산→천안", sequence_order=2, camera_id=51),
        _camera(route_id=4, route_name="천안→아산", sequence_order=1, camera_id=348),
    ]

    camera = resolve_camera(cameras, route_id=3, sequence_order=2)

    assert camera.camera_id == 51


def test_resolve_camera_rejects_ambiguous_match():
    cameras = [
        _camera(route_id=3, route_name="아산→천안", sequence_order=2, camera_id=51),
        _camera(route_id=4, route_name="천안→아산", sequence_order=14, camera_id=51),
    ]

    try:
        resolve_camera(cameras, camera_id=51)
    except ValueError as exc:
        assert "ambiguous" in str(exc).lower()
    else:
        raise AssertionError("Expected ValueError for ambiguous camera selection")


def test_resolve_camera_rejects_missing_match():
    cameras = [_camera(route_id=3, route_name="아산→천안", sequence_order=1, camera_id=261)]

    try:
        resolve_camera(cameras, route_id=4, sequence_order=1)
    except ValueError as exc:
        assert "no mapped camera" in str(exc).lower()
    else:
        raise AssertionError("Expected ValueError for missing selection")
