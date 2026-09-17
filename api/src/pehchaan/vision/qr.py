from __future__ import annotations

import logging
import threading
from pathlib import Path

import cv2
import numpy as np

logger = logging.getLogger(__name__)

WECHAT_FILES = ("detect.prototxt", "detect.caffemodel", "sr.prototxt", "sr.caffemodel")


class QrReader:
    """OpenCV WeChat QR detector: CNN detection + super-resolution, robust on dense codes in phone photos."""

    def __init__(self, models_dir: Path) -> None:
        paths = [models_dir / "wechat" / name for name in WECHAT_FILES]
        if all(p.exists() for p in paths):
            self._detector = cv2.wechat_qrcode_WeChatQRCode(*(str(p) for p in paths))
        else:
            logger.warning("WeChat QR models missing; using the non-CNN detector")
            self._detector = cv2.wechat_qrcode_WeChatQRCode()
        self._lock = threading.Lock()

    def read(self, image: np.ndarray) -> list[str]:
        attempts = [image]
        h, w = image.shape[:2]
        if max(h, w) < 1600:
            attempts.append(cv2.resize(image, None, fx=2, fy=2, interpolation=cv2.INTER_CUBIC))
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        attempts.append(cv2.cvtColor(cv2.equalizeHist(gray), cv2.COLOR_GRAY2BGR))
        for attempt in attempts:
            with self._lock:
                texts, _ = self._detector.detectAndDecode(attempt)
            if texts:
                return [t for t in texts if t]
        return []
