from __future__ import annotations

import asyncio

import cv2
import numpy as np

from pehchaan.domain.models import CheckResult, CheckStatus, Finding
from pehchaan.imaging import ImageDecodeError, decode_image, eaadhaar_passwords, render_pdf, resize_width
from pehchaan.pipeline.checks.base import Check, finding
from pehchaan.pipeline.context import VerificationContext
from pehchaan.vision.faces import FaceEngine

MIN_SIDE = 480
BLUR_THRESHOLD = 40.0  # variance of the Laplacian at 1000 px width
GLARE_BLOB_RATIO = 0.03


class QualityCheck(Check):
    """Can this image be verified at all? Failure means a retake, never a rejection."""

    name = "quality"

    def __init__(self, faces: FaceEngine | None) -> None:
        self._faces = faces

    async def run(self, ctx: VerificationContext) -> CheckResult:
        return await asyncio.to_thread(self._run, ctx)

    def _run(self, ctx: VerificationContext) -> CheckResult:
        is_pdf = ctx.id_media_type == "application/pdf"
        try:
            if is_pdf:
                form = ctx.payload.form
                image = render_pdf(ctx.id_image, eaadhaar_passwords(form.name, form.dob))
            else:
                image = decode_image(ctx.id_image)
        except ImageDecodeError:
            return self.result(CheckStatus.FAIL, finding("PDF_UNREADABLE" if is_pdf else "IMAGE_UNREADABLE"))
        ctx.image = image

        h, w = image.shape[:2]
        findings: list[Finding] = []
        work = resize_width(image, 1000)
        gray = cv2.cvtColor(work, cv2.COLOR_BGR2GRAY)
        blur = float(cv2.Laplacian(gray, cv2.CV_64F).var())
        glare = 0.0 if is_pdf else _glare_ratio(work)

        if min(h, w) < MIN_SIDE:
            findings.append(finding("IMAGE_TOO_SMALL"))
        if not is_pdf and blur < BLUR_THRESHOLD:
            findings.append(finding("IMAGE_BLURRY"))
        if glare > GLARE_BLOB_RATIO:
            findings.append(finding("IMAGE_GLARE"))

        if self._faces is not None:
            ctx.id_faces = self._faces.detect(image)

        status = CheckStatus.FAIL if findings else CheckStatus.PASS
        return self.result(
            status,
            *findings,
            width=w,
            height=h,
            blur_score=round(blur, 1),
            glare_ratio=round(glare, 4),
            faces_on_document=len(ctx.id_faces),
        )


def _glare_ratio(image: np.ndarray) -> float:
    """Largest blown-out blob that doesn't touch the border (white desks and margins don't count)."""
    mask = np.all(image >= 250, axis=2).astype(np.uint8)
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((5, 5), np.uint8))
    count, _, stats, _ = cv2.connectedComponentsWithStats(mask)
    h, w = mask.shape
    largest = 0
    for i in range(1, count):
        x, y, bw, bh, area = stats[i]
        if x > 0 and y > 0 and x + bw < w and y + bh < h:
            largest = max(largest, int(area))
    return largest / (h * w)
