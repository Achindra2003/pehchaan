"""Pixel-level signals. Soft by design: they can ask for review or a retake, never reject.

Published benchmarks put forensic detectors and vision-model judges near chance on AI-edited documents,
so these are tripwires for lazy edits, not proof. Uncalibrated signals report scores without acting.
"""

from __future__ import annotations

import asyncio
import io
import statistics

import cv2
import numpy as np
from PIL import Image

from pehchaan.domain.models import CheckResult, CheckStatus, DocType, Finding
from pehchaan.imaging import crop_box
from pehchaan.ocr.base import OcrLine
from pehchaan.pipeline.checks.base import Check, finding
from pehchaan.pipeline.context import VerificationContext

EDITORS = (b"Photoshop", b"GIMP", b"Canva", b"Picsart", b"PicsArt", b"Snapseed", b"Pixlr", b"Lightroom", b"Affinity Photo", b"paint.net", b"PhotoDirector", b"Fotor")  # fmt: skip
ELA_RATIO_HIGH = 2.5
ELA_RATIO_LOW = 0.35
ALIGNMENT_TOLERANCE = 0.035  # fraction of image width
MOIRE_THRESHOLD = 12.0


class TamperCheck(Check):
    name = "tamper"

    def __init__(self, recapture_enabled: bool) -> None:
        self._recapture_enabled = recapture_enabled

    async def run(self, ctx: VerificationContext) -> CheckResult:
        if ctx.image is None:
            return self.result(CheckStatus.SKIPPED)
        return await asyncio.to_thread(self._run, ctx)

    def _run(self, ctx: VerificationContext) -> CheckResult:
        findings: list[Finding] = []
        details: dict[str, object] = {}

        if software := _editing_software(ctx.id_image):
            findings.append(finding("EDITING_SOFTWARE_METADATA", software=software))

        is_photo = ctx.id_media_type == "image/jpeg"
        boxes = ctx.fields.boxes
        if is_photo and "dob" in boxes:
            others = [boxes[k] for k in ("name", "gender", "id_number") if k in boxes and boxes[k] != boxes["dob"]]
            if others and (ratio := _ela_ratio(ctx.image, boxes["dob"], others)) is not None:
                details["dob_ela_ratio"] = round(ratio, 2)
                if ratio > ELA_RATIO_HIGH or ratio < ELA_RATIO_LOW:
                    findings.append(finding("TAMPER_SUSPECTED_FIELD", field="date of birth"))

        if ctx.fields.doc_type is DocType.AADHAAR and ctx.ocr is not None:
            if (offset := _dob_alignment_offset(ctx)) is not None:
                details["dob_alignment_offset"] = round(offset, 3)
                if offset > ALIGNMENT_TOLERANCE:
                    findings.append(finding("TEXT_GEOMETRY_ANOMALY", field="date of birth"))

        if is_photo:
            moire = _moire_score(ctx.image)
            details["moire_score"] = round(moire, 2)
            if self._recapture_enabled and moire > MOIRE_THRESHOLD:
                findings.append(finding("SCREEN_RECAPTURE"))

        return self.result(CheckStatus.WARN if findings else CheckStatus.PASS, *findings, **details)


def _editing_software(data: bytes) -> str | None:
    try:
        with Image.open(io.BytesIO(data)) as image:
            software = str(image.getexif().get(0x0131, ""))
    except Exception:
        software = ""
    head = data[:131072]
    for editor in EDITORS:
        if editor.decode() in software or editor in head:
            return editor.decode()
    return None


def _ela_ratio(image: np.ndarray, target: tuple, others: list[tuple]) -> float | None:
    """Error level of the DOB box relative to other text boxes after a quality-90 re-save.

    A region pasted in from a different source recompresses differently from its neighbours.
    """
    ok, buffer = cv2.imencode(".jpg", image, [cv2.IMWRITE_JPEG_QUALITY, 90])
    if not ok:
        return None
    resaved = cv2.imdecode(buffer, cv2.IMREAD_COLOR)
    diff = cv2.absdiff(image, resaved).astype(np.float32).mean(axis=2)
    target_level = float(crop_box(diff, target, pad=0.1).mean()) if crop_box(diff, target).size else 0.0
    levels = [float(crop_box(diff, box, pad=0.1).mean()) for box in others if crop_box(diff, box).size]
    baseline = statistics.median(levels) if levels else 0.0
    return target_level / baseline if baseline > 0.05 else None


def _dob_alignment_offset(ctx: VerificationContext) -> float | None:
    """On the Aadhaar front, name, DOB and gender share a left margin; a pasted DOB line often doesn't."""
    boxes = ctx.fields.boxes
    if not {"name", "dob", "gender"} <= boxes.keys() or boxes["dob"] == boxes["gender"]:
        return None
    lines: list[OcrLine] = ctx.ocr.lines if ctx.ocr else []
    by_box = {line.box: line for line in lines}
    if boxes["name"] not in by_box or boxes["gender"] not in by_box:
        return None
    anchors = [boxes["name"][0], boxes["gender"][0]]
    if abs(anchors[0] - anchors[1]) > ALIGNMENT_TOLERANCE:
        return None  # layout isn't the standard column (e.g. a PVC card variant)
    return abs(boxes["dob"][0] - statistics.mean(anchors))


def _moire_score(image: np.ndarray) -> float:
    """Peak-to-median ratio of mid/high-frequency spectrum energy; screens produce sharp periodic peaks."""
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY).astype(np.float32)
    h, w = gray.shape
    size = min(512, h, w)
    y0, x0 = (h - size) // 2, (w - size) // 2
    patch = gray[y0 : y0 + size, x0 : x0 + size]
    patch = (patch - patch.mean()) * np.outer(np.hanning(size), np.hanning(size))
    spectrum = np.log1p(np.abs(np.fft.fftshift(np.fft.fft2(patch))))
    yy, xx = np.mgrid[:size, :size]
    radius = np.hypot(yy - size / 2, xx - size / 2)
    band = spectrum[(radius > size * 0.15) & (radius < size * 0.45)]
    return float(band.max() / (np.median(band) + 1e-6))
