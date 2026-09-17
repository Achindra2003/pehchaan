"""Checks still to be built. Each docstring is the spec; see docs/BUILD_PLAN.md for owners.

Move a check into its own module when implementing it.
"""

from __future__ import annotations

from pehchaan.domain.models import CheckResult
from pehchaan.pipeline.checks.base import Check
from pehchaan.pipeline.context import VerificationContext


class QualityCheck(Check):
    """Stream B. Laplacian-variance blur, glare on the card region, card contour, minimum
    resolution, face present on the ID (YuNet), screen moiré (FFT). FAIL stops the pipeline.
    Codes: IMAGE_BLURRY, IMAGE_GLARE, IMAGE_TOO_SMALL, DOCUMENT_NOT_FOUND, SCREEN_RECAPTURE."""

    name = "quality"

    async def run(self, ctx: VerificationContext) -> CheckResult:
        return self.not_implemented()


class ExtractCheck(Check):
    """Stream B. Parse `payload.textract_response` when present; otherwise call Textract
    (DetectDocumentText, then AnalyzeDocument Queries for missing fields). Classify doc type from
    anchor text. Fill `ctx.fields` with per-field confidence and dob_source=OCR.
    PASS when doc type, name and (DOB or YOB) are read. Codes: FIELDS_UNREADABLE,
    DOC_TYPE_UNKNOWN, LOW_OCR_CONFIDENCE."""

    name = "extract"

    async def run(self, ctx: VerificationContext) -> CheckResult:
        return self.not_implemented()


class AadhaarQrCheck(Check):
    """Stream C. WeChat QR detect → base-10 bigint → gzip → split on 255 → verify the last
    256 bytes (SHA256withRSA, UIDAI certificate) → compare QR name/DOB/gender with OCR and
    form, QR photo with printed photo. On success set ctx.fields.dob_source=QR_SIGNED.
    Never persist QR data. PASS only when signature is valid AND data matches the print.
    Codes: AADHAAR_QR_VERIFIED, AADHAAR_QR_NOT_FOUND, AADHAAR_QR_SIGNATURE_INVALID,
    AADHAAR_PRINT_CONTRADICTS_QR, AADHAAR_PHOTO_MISMATCH_QR."""

    name = "aadhaar_qr"

    async def run(self, ctx: VerificationContext) -> CheckResult:
        return self.not_implemented()


class TamperCheck(Check):
    """Stream D. Soft signals only: noise/compression inconsistency inside DOB and name boxes
    versus the card baseline, text-line geometry from Textract boxes, editing-software EXIF,
    optional vision-model second opinion. Codes: TAMPER_SUSPECTED_FIELD,
    EDITING_SOFTWARE_METADATA, TEXT_GEOMETRY_ANOMALY."""

    name = "tamper"

    async def run(self, ctx: VerificationContext) -> CheckResult:
        return self.not_implemented()


class DuplicatesCheck(Check):
    """Stream C. HMAC(pepper, doctype:number) lookup; PDQ hash of the card crop; SFace embedding
    of the ID face; platform-wide. Same ID + matching name = SAME_PERSON_KNOWN. Conflicts go to
    review for BOTH registrations. Codes: DUPLICATE_ID_OTHER_IDENTITY, DUPLICATE_IMAGE,
    DUPLICATE_FACE_OTHER_IDENTITY, SAME_PERSON_KNOWN."""

    name = "duplicates"

    async def run(self, ctx: VerificationContext) -> CheckResult:
        return self.not_implemented()


class IdentityCheck(Check):
    """Stream D. indic-namematch between form, OCR and QR names; DOB form vs document; college
    email domain vs institution (AISHE). PASS when name and DOB agree.
    Codes: NAME_MATCH, NAME_PARTIAL_MATCH, NAME_MISMATCH, DOB_MISMATCH_FORM,
    EMAIL_DOMAIN_MATCHES_INSTITUTION, INSTITUTION_NOT_RECOGNISED."""

    name = "identity"

    async def run(self, ctx: VerificationContext) -> CheckResult:
        return self.not_implemented()


class SelfieCheck(Check):
    """Stream D. MiniFASNet anti-spoofing on the selfie, then SFace similarity against the QR
    photo (preferred) or the printed ID photo. SKIPPED when no selfie and not required.
    Codes: SELFIE_MATCH, SELFIE_MISMATCH, SELFIE_SPOOF_SUSPECTED, SELFIE_REQUIRED."""

    name = "selfie"

    async def run(self, ctx: VerificationContext) -> CheckResult:
        return self.not_implemented()
