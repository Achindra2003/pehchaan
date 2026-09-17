"""Local OCR fallback: PaddleOCR models on ONNX Runtime (RapidOCR). CPU only, no network.

Measured on a 16-thread laptop, concurrency inside one Python process doesn't raise throughput (the pipeline is
CPU-bound), so Pehchaan scales by adding processes/containers behind the queue, not threads. See scripts/loadtest.py.
"""

from __future__ import annotations

import queue

import numpy as np

from pehchaan.ocr.base import OcrLine, OcrResult

_THREADS = {
    f"{part}_{kind}_op_num_threads": n for part in ("det", "cls", "rec") for kind, n in (("intra", 2), ("inter", 1))
}


class RapidOcrEngine:
    def __init__(self, size: int = 1) -> None:
        from rapidocr_onnxruntime import RapidOCR

        self._pool: queue.Queue = queue.Queue()
        for _ in range(max(1, size)):
            self._pool.put(RapidOCR(**_THREADS))

    def read(self, image: np.ndarray) -> OcrResult:
        h, w = image.shape[:2]
        engine = self._pool.get()
        try:
            raw, _ = engine(image)
        finally:
            self._pool.put(engine)
        lines: list[OcrLine] = []
        for points, text, score in raw or []:
            xs = [p[0] for p in points]
            ys = [p[1] for p in points]
            lines.append(OcrLine(str(text), float(score), (min(xs) / w, min(ys) / h, max(xs) / w, max(ys) / h)))
        lines.sort(key=lambda line: (round(line.box[1], 2), line.box[0]))
        return OcrResult(lines=lines, provider="rapidocr")
