"""YOLOv8 bus detection using ONNX Runtime with DirectML acceleration."""

import logging
from pathlib import Path

import cv2
import numpy as np
import onnxruntime as ort

from app.config import settings

logger = logging.getLogger(__name__)

_session: ort.InferenceSession | None = None


def _get_session() -> ort.InferenceSession:
    global _session
    if _session is None:
        model_path = Path(settings.yolo_model_path)
        if not model_path.exists():
            raise FileNotFoundError(
                f"YOLO ONNX model not found at {model_path}. "
                "Export with: yolo export model=yolov8n.pt format=onnx"
            )
        providers = ["CPUExecutionProvider"]
        _session = ort.InferenceSession(str(model_path), providers=providers)
        actual = _session.get_providers()
        logger.info("ONNX Runtime providers: %s", actual)
    return _session


def _preprocess(image: np.ndarray, input_size: int = 640) -> tuple[np.ndarray, float, tuple[int, int]]:
    """Resize + pad + normalize an image for YOLOv8 input."""
    h, w = image.shape[:2]
    scale = min(input_size / h, input_size / w)
    nh, nw = int(h * scale), int(w * scale)
    resized = cv2.resize(image, (nw, nh))

    canvas = np.full((input_size, input_size, 3), 114, dtype=np.uint8)
    canvas[:nh, :nw, :] = resized

    blob = canvas.astype(np.float32) / 255.0
    blob = blob.transpose(2, 0, 1)[np.newaxis, ...]  # (1, 3, 640, 640)
    return blob, scale, (nh, nw)


def _postprocess(
    output: np.ndarray,
    scale: float,
    conf_threshold: float,
    bus_class_id: int,
) -> list[dict]:
    """Parse YOLOv8 output tensor into bus detections."""
    # YOLOv8 output shape: (1, 84, 8400) — transpose to (8400, 84)
    predictions = output[0].T  # (8400, 84)

    detections = []
    for pred in predictions:
        cx, cy, w, h = pred[:4]
        class_scores = pred[4:]
        class_id = int(np.argmax(class_scores))
        confidence = float(class_scores[class_id])

        if class_id != bus_class_id or confidence < conf_threshold:
            continue

        x1 = (cx - w / 2) / scale
        y1 = (cy - h / 2) / scale
        x2 = (cx + w / 2) / scale
        y2 = (cy + h / 2) / scale

        detections.append({
            "bbox": [float(x1), float(y1), float(x2), float(y2)],
            "confidence": confidence,
            "class_id": class_id,
        })

    # NMS — simple IoU-based filtering
    detections.sort(key=lambda d: d["confidence"], reverse=True)
    keep = []
    for det in detections:
        overlap = False
        for kept in keep:
            if _iou(det["bbox"], kept["bbox"]) > 0.5:
                overlap = True
                break
        if not overlap:
            keep.append(det)

    return keep


def _iou(box_a: list[float], box_b: list[float]) -> float:
    x1 = max(box_a[0], box_b[0])
    y1 = max(box_a[1], box_b[1])
    x2 = min(box_a[2], box_b[2])
    y2 = min(box_a[3], box_b[3])
    inter = max(0, x2 - x1) * max(0, y2 - y1)
    area_a = (box_a[2] - box_a[0]) * (box_a[3] - box_a[1])
    area_b = (box_b[2] - box_b[0]) * (box_b[3] - box_b[1])
    union = area_a + area_b - inter
    return inter / union if union > 0 else 0.0


def detect_buses(image: np.ndarray) -> list[dict]:
    """Run YOLOv8n inference and return bus detections.

    Returns a list of dicts with keys: bbox, confidence, class_id.
    """
    session = _get_session()
    blob, scale, _ = _preprocess(image)

    input_name = session.get_inputs()[0].name
    outputs = session.run(None, {input_name: blob})

    return _postprocess(
        outputs[0],
        scale,
        settings.yolo_confidence_threshold,
        settings.bus_class_id,
    )


def detect_buses_from_jpeg(jpeg_bytes: bytes) -> list[dict]:
    """Convenience: decode JPEG bytes and detect buses."""
    arr = np.frombuffer(jpeg_bytes, dtype=np.uint8)
    image = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if image is None:
        return []
    return detect_buses(image)
