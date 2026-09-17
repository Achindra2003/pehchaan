from __future__ import annotations

import asyncio

from pehchaan.domain.models import CaptureSource, CheckResult, CheckStatus, Finding
from pehchaan.imaging import ImageDecodeError, decode_image
from pehchaan.pipeline.checks.base import Check, finding
from pehchaan.pipeline.context import VerificationContext
from pehchaan.vision.faces import FaceEngine

MATCH_THRESHOLD = 0.33  # SFace cosine; OpenCV's 0.363 assumes two good photos, ID prints are worse


class SelfieCheck(Check):
    """Is the person holding the phone the person on the ID? Only a live camera capture can reach L4."""

    name = "selfie"

    def __init__(self, faces: FaceEngine | None, liveness_enabled: bool, liveness_threshold: float) -> None:
        self._faces = faces
        self._liveness_enabled = liveness_enabled
        self._liveness_threshold = liveness_threshold

    async def run(self, ctx: VerificationContext) -> CheckResult:
        if ctx.selfie is None:
            if ctx.policy.require_selfie:
                return self.result(CheckStatus.FAIL, finding("SELFIE_REQUIRED"))
            return self.result(CheckStatus.SKIPPED)
        if self._faces is None:
            return self.result(CheckStatus.ERROR, note="face models unavailable")
        return await asyncio.to_thread(self._run, ctx)

    def _run(self, ctx: VerificationContext) -> CheckResult:
        if self._faces is None:
            return self.result(CheckStatus.ERROR)
        try:
            image = decode_image(ctx.selfie or b"")
        except ImageDecodeError:
            return self.result(CheckStatus.FAIL, finding("SELFIE_NO_FACE"))
        faces = self._faces.detect(image)
        if not faces:
            return self.result(CheckStatus.FAIL, finding("SELFIE_NO_FACE"))

        findings: list[Finding] = []
        details: dict[str, object] = {}
        if self._liveness_enabled:
            live = self._faces.liveness(image, faces[0])
            details["liveness"] = round(live, 3)
            if live < self._liveness_threshold:
                return self.result(CheckStatus.FAIL, finding("SELFIE_SPOOF_SUSPECTED"), **details)

        live_capture = ctx.payload.capture.selfie_source is CaptureSource.CAMERA
        if not live_capture:
            findings.append(finding("SELFIE_NOT_LIVE_CAPTURE"))

        selfie = self._faces.embed(image, faces[0])
        references = {}
        if ctx.qr_photo_embedding is not None:
            references["signed_qr_photo"] = self._faces.similarity(selfie, ctx.qr_photo_embedding)
        if ctx.id_face_embedding is not None:
            references["printed_photo"] = self._faces.similarity(selfie, ctx.id_face_embedding)
        elif ctx.image is not None and ctx.id_faces:
            references["printed_photo"] = self._faces.similarity(selfie, self._faces.embed(ctx.image, ctx.id_faces[0]))
        details["similarity"] = {k: round(v, 3) for k, v in references.items()}

        if not references:
            return self.result(CheckStatus.SKIPPED, finding("SELFIE_NO_REFERENCE"), *findings, **details)
        if max(references.values()) < MATCH_THRESHOLD:
            return self.result(CheckStatus.WARN, finding("SELFIE_MISMATCH"), *findings, **details)
        status = CheckStatus.PASS if live_capture else CheckStatus.WARN
        return self.result(status, finding("SELFIE_MATCH"), *findings, **details)
