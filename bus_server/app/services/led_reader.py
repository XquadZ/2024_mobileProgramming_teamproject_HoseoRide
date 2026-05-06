"""LED destination sign reader — optional confidence booster using OCR."""

import logging

import cv2
import numpy as np

logger = logging.getLogger(__name__)

SHUTTLE_KEYWORDS = ["호서", "아산", "천안", "셔틀", "Hoseo"]

_reader = None


def _get_reader():
    global _reader
    if _reader is None:
        try:
            import easyocr
            _reader = easyocr.Reader(["ko", "en"], gpu=False)
        except ImportError:
            logger.warning("easyocr not installed — LED reading disabled")
            return None
    return _reader


def read_led_sign(image: np.ndarray, bbox: list[float]) -> str | None:
    """Attempt to read the LED destination sign from the top portion of a detected bus.

    Args:
        image: Full camera frame (BGR).
        bbox: Bus bounding box [x1, y1, x2, y2].

    Returns:
        Detected text if a shuttle keyword is found, else None.
    """
    reader = _get_reader()
    if reader is None:
        return None

    x1, y1, x2, y2 = [int(v) for v in bbox]
    h = y2 - y1
    # LED sign is typically in the top 20% of the bus bounding box
    led_y2 = y1 + int(h * 0.2)
    led_crop = image[max(0, y1):max(0, led_y2), max(0, x1):max(0, x2)]

    if led_crop.size == 0:
        return None

    # Enhance contrast for LED text
    gray = cv2.cvtColor(led_crop, cv2.COLOR_BGR2GRAY)
    enhanced = cv2.equalizeHist(gray)

    try:
        results = reader.readtext(enhanced)
    except Exception:
        logger.debug("OCR failed on LED crop")
        return None

    for _, text, conf in results:
        if conf < 0.3:
            continue
        for keyword in SHUTTLE_KEYWORDS:
            if keyword in text:
                logger.info("LED sign detected: '%s' (conf=%.2f)", text, conf)
                return text

    return None
