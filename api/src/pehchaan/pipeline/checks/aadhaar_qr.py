from __future__ import annotations

import asyncio
import io

import cv2
import numpy as np
from PIL import Image

from pehchaan.domain.models import CheckResult, CheckStatus, DocType, FieldSource, Finding
from pehchaan.names import REJECT_BELOW, name_score
from pehchaan.pipeline.checks.base import Check, finding
from pehchaan.pipeline.context import VerificationContext
from pehchaan.vision.faces import FaceEngine

PHOTO_MISMATCH_BELOW = 0.2  # SFace cosine; printed ID photos and QR thumbnails are low quality


class AadhaarQrCheck(Check):
    """Cryptographic proof: the UIDAI-signed QR must agree with what is printed on the card.

    Only one contradiction is treated as hard evidence: the printed DOB differs from the signed DOB
    *and* matches what the participant typed into the form. A misread would not also match the form.
    """

    name = "aadhaar_qr"

    def __init__(self, faces: FaceEngine | None, certificates_available: bool) -> None:
        self._faces = faces
        self._certificates_available = certificates_available

    async def run(self, ctx: VerificationContext) -> CheckResult:
        return await asyncio.to_thread(self._run, ctx)

    def _run(self, ctx: VerificationContext) -> CheckResult:
        qr, fields, form = ctx.qr, ctx.fields, ctx.payload.form
        if qr is None:
            if fields.doc_type is not DocType.AADHAAR:
                return self.result(CheckStatus.SKIPPED)
            policy = ctx.policy
            if policy.require_aadhaar_qr and (policy.min_age is not None or policy.max_age is not None):
                # A printed DOB alone is exactly what a pixel edit targets; ask once, then hand to a person.
                code = "AADHAAR_QR_MISSING_AFTER_RETAKE" if ctx.previous_attempts else "AADHAAR_QR_REQUIRED"
                return self.result(CheckStatus.FAIL, finding(code))
            return self.result(CheckStatus.SKIPPED, finding("AADHAAR_QR_NOT_FOUND"))
        if qr.legacy_unsigned:
            return self.result(CheckStatus.SKIPPED, finding("AADHAAR_QR_LEGACY_UNSIGNED"))
        if not self._certificates_available:
            return self.result(CheckStatus.SKIPPED, finding("AADHAAR_QR_CERT_MISSING"))
        if ctx.qr_certificate is None:
            return self.result(CheckStatus.WARN, finding("AADHAAR_QR_SIGNATURE_INVALID"))

        findings: list[Finding] = []
        hard = False
        print_is_ocr = fields.dob_source is FieldSource.OCR

        # Date of birth
        if print_is_ocr and fields.dob and qr.dob and fields.dob != qr.dob:
            if form.dob == fields.dob:
                findings.append(finding("AADHAAR_PRINT_CONTRADICTS_QR", field="date of birth"))
                hard = True
            else:
                findings.append(finding("AADHAAR_PRINT_QR_MISMATCH", field="date of birth"))
        printed_year = fields.dob.year if fields.dob else fields.year_of_birth
        signed_year = qr.dob.year if qr.dob else qr.year_of_birth
        if print_is_ocr and not findings and printed_year and signed_year and printed_year != signed_year:
            findings.append(finding("AADHAAR_PRINT_QR_MISMATCH", field="year of birth"))

        # Name and number: differences here are more often OCR or transliteration than fraud
        if fields.name and name_score(fields.name, qr.name) < REJECT_BELOW:
            findings.append(finding("AADHAAR_PRINT_QR_MISMATCH", field="name"))
        printed_last4 = fields.id_last4
        if (
            printed_last4
            and qr.last4
            and printed_last4 != qr.last4
            and fields.id_number
            and not fields.id_number.startswith("XXXX")
        ):
            findings.append(finding("AADHAAR_PRINT_QR_MISMATCH", field="Aadhaar number"))

        photo_similarity = self._photo_similarity(ctx)
        if photo_similarity is not None and photo_similarity < PHOTO_MISMATCH_BELOW:
            findings.append(finding("AADHAAR_PHOTO_MISMATCH_QR"))

        details = {"certificate": ctx.qr_certificate, "qr_version": qr.version, "photo_similarity": photo_similarity}
        if hard:
            return self.result(CheckStatus.FAIL, *findings, **details)
        if findings:
            return self.result(CheckStatus.WARN, *findings, **details)

        # Signed data agrees with the card: it becomes the authoritative source.
        update: dict[str, object] = {"dob_source": FieldSource.QR_SIGNED}
        if qr.dob:
            update["dob"] = qr.dob
            update["year_of_birth"] = None
        ctx.fields = fields.model_copy(update=update)
        return self.result(CheckStatus.PASS, finding("AADHAAR_QR_VERIFIED"), **details)

    def _photo_similarity(self, ctx: VerificationContext) -> float | None:
        if self._faces is None or ctx.qr is None or not ctx.qr.photo or not ctx.id_faces or ctx.image is None:
            return None
        try:
            with Image.open(io.BytesIO(ctx.qr.photo)) as photo:
                portrait = cv2.cvtColor(np.asarray(photo.convert("RGB")), cv2.COLOR_RGB2BGR)
        except Exception:
            return None
        qr_embedding = self._faces.embed_portrait(portrait)
        if qr_embedding is None:
            return None
        ctx.qr_photo_embedding = qr_embedding
        printed = self._faces.embed(ctx.image, ctx.id_faces[0])
        return round(self._faces.similarity(qr_embedding, printed), 3)
