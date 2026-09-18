"""Face detection (YuNet), matching (SFace) and passive liveness (MiniFASNet-V2), all ONNX on CPU."""

from __future__ import annotations

import logging
import queue
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np

logger = logging.getLogger(__name__)

YUNET = "face_detection_yunet_2023mar.onnx"
SFACE = "face_recognition_sface_2021dec.onnx"
MINIFASNET = "minifasnet_v2.onnx"
DEFAULT_LIVE_CLASS = 0  # model card: [live, print attack, replay attack]


@dataclass(frozen=True)
class Face:
    row: np.ndarray  # YuNet output row in image coordinates: bbox(4), landmarks(10), score

    @property
    def box(self) -> tuple[int, int, int, int]:
        x, y, w, h = self.row[:4]
        return int(x), int(y), int(w), int(h)

    @property
    def area(self) -> int:
        return self.box[2] * self.box[3]


class FaceEngine:
    def __init__(self, models_dir: Path, size: int = 4, live_class: int = DEFAULT_LIVE_CLASS) -> None:
        self._live_class = live_class
        import onnxruntime as ort

        # OpenCV DNN models aren't thread-safe: one detector/recogniser pair per concurrent verification.
        self._pool: queue.Queue = queue.Queue()
        for _ in range(max(1, size)):
            self._pool.put(
                (
                    cv2.FaceDetectorYN.create(str(models_dir / YUNET), "", (320, 320), 0.6, 0.3, 5000),
                    cv2.FaceRecognizerSF.create(str(models_dir / SFACE), ""),
                )
            )
        options = ort.SessionOptions()
        options.intra_op_num_threads = 1
        self._liveness = ort.InferenceSession(str(models_dir / MINIFASNET), options, providers=["CPUExecutionProvider"])

    @classmethod
    def load(cls, models_dir: Path, size: int = 4, live_class: int = DEFAULT_LIVE_CLASS) -> FaceEngine | None:
        missing = [name for name in (YUNET, SFACE, MINIFASNET) if not (models_dir / name).exists()]
        if missing:
            logger.warning("face models missing (%s); run scripts/download_models.py", ", ".join(missing))
            return None
        return cls(models_dir, size, live_class)

    @contextmanager
    def _models(self):
        models = self._pool.get()
        try:
            yield models
        finally:
            self._pool.put(models)

    def detect(self, image: np.ndarray) -> list[Face]:
        h, w = image.shape[:2]
        scale = min(1.0, 1280 / max(h, w))
        resized = cv2.resize(image, (round(w * scale), round(h * scale))) if scale < 1 else image
        with self._models() as (detector, _):
            detector.setInputSize((resized.shape[1], resized.shape[0]))
            _, rows = detector.detect(resized)
        faces = []
        for row in rows if rows is not None else []:
            scaled = row.copy()
            scaled[:14] /= scale
            faces.append(Face(scaled))
        return sorted(faces, key=lambda f: f.area, reverse=True)

    def embed(self, image: np.ndarray, face: Face) -> np.ndarray:
        with self._models() as (_, recognizer):
            feature = recognizer.feature(recognizer.alignCrop(image, face.row))
        return _normalise(feature)

    def embed_portrait(self, image: np.ndarray) -> np.ndarray | None:
        """Embed a small portrait (e.g. the Secure QR photo): detect if possible, otherwise use the whole crop."""
        upscaled = cv2.resize(image, None, fx=3, fy=3, interpolation=cv2.INTER_CUBIC)
        if faces := self.detect(upscaled):
            return self.embed(upscaled, faces[0])
        with self._models() as (_, recognizer):
            feature = recognizer.feature(cv2.resize(image, (112, 112)))
        return _normalise(feature)

    def liveness(self, image: np.ndarray, face: Face) -> float:
        crop = _liveness_crop(image, face.box, scale=2.7)
        tensor = (cv2.resize(crop, (80, 80)).astype(np.float32) / 255.0).transpose(2, 0, 1)[None]
        logits = self._liveness.run(None, {self._liveness.get_inputs()[0].name: tensor})[0][0]
        probs = np.exp(logits - logits.max())
        probs /= probs.sum()
        return float(probs[self._live_class])

    @staticmethod
    def similarity(a: np.ndarray, b: np.ndarray) -> float:
        return float(np.dot(a, b))


def _normalise(feature: np.ndarray) -> np.ndarray:
    vector = feature.flatten().astype(np.float32)
    return vector / (np.linalg.norm(vector) or 1.0)


def _liveness_crop(image: np.ndarray, box: tuple[int, int, int, int], scale: float) -> np.ndarray:
    """Silent-Face-Anti-Spoofing crop: box scaled around its centre, shifted to stay inside the image."""
    src_h, src_w = image.shape[:2]
    x, y, w, h = box
    w, h = max(w, 1), max(h, 1)
    scale = min((src_h - 1) / h, (src_w - 1) / w, scale)
    new_w, new_h = w * scale, h * scale
    cx, cy = x + w / 2, y + h / 2
    x0, y0 = max(0.0, cx - new_w / 2), max(0.0, cy - new_h / 2)
    x1, y1 = min(src_w - 1.0, x0 + new_w), min(src_h - 1.0, y0 + new_h)
    x0, y0 = max(0.0, x1 - new_w), max(0.0, y1 - new_h)
    return image[int(y0) : int(y1) + 1, int(x0) : int(x1) + 1]
