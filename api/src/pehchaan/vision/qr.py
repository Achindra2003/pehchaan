from __future__ import annotations

import logging
import queue
from pathlib import Path

import cv2
import numpy as np

logger = logging.getLogger(__name__)

WECHAT_FILES = ("detect.prototxt", "detect.caffemodel", "sr.prototxt", "sr.caffemodel")


class QrReader:
    """OpenCV WeChat QR detector: CNN detection + super-resolution, robust on dense codes in phone photos."""

    def __init__(self, models_dir: Path, size: int = 4) -> None:
        paths = [models_dir / "wechat" / name for name in WECHAT_FILES]
        use_cnn = all(p.exists() for p in paths)
        if not use_cnn:
            logger.warning("WeChat QR models missing; using the non-CNN detector")
        # OpenCV detectors aren't thread-safe; a small pool lets concurrent verifications decode in parallel.
        self._pool: queue.Queue = queue.Queue()
        for _ in range(max(1, size)):
            detector = (
                cv2.wechat_qrcode_WeChatQRCode(*(str(p) for p in paths))
                if use_cnn
                else cv2.wechat_qrcode_WeChatQRCode()
            )
            self._pool.put(detector)

    def read(self, image: np.ndarray) -> list[str]:
        attempts = [image]
        h, w = image.shape[:2]
        if max(h, w) < 1600:
            attempts.append(cv2.resize(image, None, fx=2, fy=2, interpolation=cv2.INTER_CUBIC))
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        attempts.append(cv2.cvtColor(cv2.equalizeHist(gray), cv2.COLOR_GRAY2BGR))
        detector = self._pool.get()
        try:
            for attempt in attempts:
                texts, _ = detector.detectAndDecode(attempt)
                if texts:
                    return [t for t in texts if t]
        finally:
            self._pool.put(detector)
        return []
