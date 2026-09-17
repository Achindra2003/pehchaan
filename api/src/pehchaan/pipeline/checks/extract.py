from __future__ import annotations

import asyncio
import logging

from pehchaan.aadhaar import secure_qr
from pehchaan.aadhaar.secure_qr import CertificateStore, SecureQrError
from pehchaan.documents.classify import classify
from pehchaan.documents.parse import clean_name, extract_fields, missing_queries
from pehchaan.domain.models import CheckResult, CheckStatus, DocType, FieldSource, Finding
from pehchaan.imaging import to_jpeg
from pehchaan.ocr.base import OcrResult
from pehchaan.ocr.rapid import RapidOcrEngine
from pehchaan.ocr.textract import TextractClient, parse_textract
from pehchaan.pipeline.checks.base import Check, finding
from pehchaan.pipeline.context import VerificationContext
from pehchaan.vision.qr import QrReader

logger = logging.getLogger(__name__)

LOW_CONFIDENCE = 0.8
KEY_FIELDS = ("name", "dob", "id_number")


class ExtractCheck(Check):
    """Read the document: OCR (Hackingly's Textract JSON first) and the Aadhaar Secure QR, in parallel."""

    name = "extract"

    def __init__(
        self,
        qr: QrReader,
        certificates: CertificateStore,
        textract: TextractClient | None,
        rapid: RapidOcrEngine | None,
        use_queries: bool,
    ) -> None:
        self._qr = qr
        self._certificates = certificates
        self._textract = textract
        self._rapid = rapid
        self._use_queries = use_queries

    async def run(self, ctx: VerificationContext) -> CheckResult:
        if ctx.image is None:
            return self.result(CheckStatus.SKIPPED, note="no usable image")
        ocr, _ = await asyncio.gather(asyncio.to_thread(self._ocr, ctx), asyncio.to_thread(self._read_qr, ctx))
        ctx.ocr = ocr

        doc_type, scores = classify(ocr.text) if ocr else (DocType.UNKNOWN, {})
        if doc_type is DocType.UNKNOWN and ctx.qr is not None:
            doc_type = DocType.AADHAAR
        fields = extract_fields(ocr, doc_type) if ocr else ctx.fields.model_copy(update={"doc_type": doc_type})

        query_pages = 0
        if ocr and self._textract and self._use_queries and (wanted := missing_queries(fields)):
            try:
                ocr.queries |= await asyncio.to_thread(self._textract.query, to_jpeg(ctx.image), wanted)
                fields = extract_fields(ocr, doc_type)
                query_pages = 1
            except Exception as exc:  # Textract outage must not block the participant
                logger.warning("textract queries failed: %s", type(exc).__name__)

        ctx.fields = self._merge_signed_qr(ctx, fields)
        result = self._assess(ctx, ocr, scores)
        result.details["textract_detect_pages"] = int(bool(ocr) and ocr.provider == "textract")
        result.details["textract_query_pages"] = query_pages
        return result

    def _ocr(self, ctx: VerificationContext) -> OcrResult | None:
        if ctx.payload.textract_response:
            return parse_textract(ctx.payload.textract_response, provider="textract:hackingly")
        if self._textract is not None:
            try:
                return self._textract.detect(to_jpeg(ctx.image))
            except Exception as exc:
                logger.warning("textract failed, falling back: %s", type(exc).__name__)
        if self._rapid is not None:
            return self._rapid.read(ctx.image)
        return None

    def _read_qr(self, ctx: VerificationContext) -> None:
        for text in self._qr.read(ctx.image):
            try:
                ctx.qr = secure_qr.decode(text)
            except SecureQrError:
                continue
            ctx.qr_certificate = self._certificates.verify(ctx.qr)
            return

    @staticmethod
    def _merge_signed_qr(ctx: VerificationContext, fields):
        """Fill gaps from the QR only when its UIDAI signature verified. Comparison happens in aadhaar_qr."""
        qr = ctx.qr
        if qr is None or ctx.qr_certificate is None:
            return fields
        update: dict[str, object] = {}
        if not fields.name and (name := clean_name(qr.name)):
            update["name"] = name
        if fields.dob is None and fields.year_of_birth is None and (qr.dob or qr.year_of_birth):
            update |= {"dob": qr.dob, "year_of_birth": qr.year_of_birth, "dob_source": FieldSource.QR_SIGNED}
        if not fields.gender and qr.gender:
            update["gender"] = qr.gender
        if not fields.id_number and qr.last4:
            update["id_number"] = f"XXXXXXXX{qr.last4}"
        return fields.model_copy(update=update) if update else fields

    @staticmethod
    def _assess(ctx: VerificationContext, ocr: OcrResult | None, scores) -> CheckResult:
        fields = ctx.fields
        details = {
            "provider": ocr.provider if ocr else None,
            "doc_type": fields.doc_type.value,
            "doc_type_scores": {k.value: v for k, v in scores.items() if v},
            "lines_read": len(ocr.lines) if ocr else 0,
            "qr_found": ctx.qr is not None,
            "fields_found": sorted(k for k in ("name", "dob", "year_of_birth", "gender", "id_number", "institution", "valid_until") if getattr(fields, k)),
        }  # fmt: skip
        if (ocr is None or not ocr.lines) and ctx.qr is None:
            return Check.result_for("extract", CheckStatus.FAIL, [finding("FIELDS_UNREADABLE", fields="text")], details)

        findings: list[Finding] = []
        if fields.doc_type is DocType.UNKNOWN:
            findings.append(finding("DOC_TYPE_UNKNOWN"))

        needed = ["name", "institution"] if fields.doc_type is DocType.COLLEGE_ID else ["name", "date of birth"]
        have = {
            "name": fields.name,
            "institution": fields.institution,
            "date of birth": fields.dob or fields.year_of_birth,
        }
        missing = [label for label in needed if not have[label]]
        if missing:
            findings.append(finding("FIELDS_UNREADABLE", fields=" and ".join(missing)))

        low = [k.replace("_", " ") for k in KEY_FIELDS if fields.confidence.get(k, 1.0) < LOW_CONFIDENCE]
        if low:
            findings.append(finding("LOW_OCR_CONFIDENCE", fields=", ".join(low)))

        status = CheckStatus.PASS if fields.doc_type is not DocType.UNKNOWN and not missing else CheckStatus.FAIL
        return Check.result_for("extract", status, findings, details)
