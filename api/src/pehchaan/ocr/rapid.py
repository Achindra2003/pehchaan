"""Local OCR fallback: PaddleOCR models on ONNX Runtime (RapidOCR). CPU only, no network."""

from __future__ import annotations

import threading

import numpy as np

from pehchaan.ocr.base import OcrLine, OcrResult


class RapidOcrEngine:
    def __init__(self) -> None:
        from rapidocr_onnxruntime import RapidOCR

        self._engine = RapidOCR()
        self._lock = threading.Lock()

    def read(self, image: np.ndarray) -> OcrResult:
        h, w = image.shape[:2]
        with self._lock:
            raw, _ = self._engine(image)
        lines: list[OcrLine] = []
        for points, text, score in raw or []:
            xs = [p[0] for p in points]
            ys = [p[1] for p in points]
            box = (min(xs) / w, min(ys) / h, max(xs) / w, max(ys) / h)
            lines.append(OcrLine(str(text), float(score), box))
        lines.sort(key=lambda line: (round(line.box[1], 2), line.box[0]))
        return OcrResult(lines=lines, provider="rapidocr")
