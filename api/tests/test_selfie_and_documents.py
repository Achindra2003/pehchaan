"""Face matching and the less common documents.

The problem statement asks for a face match when a selfie is provided, and for extraction across common Indian
IDs. Specimen cards carry no real faces, so the selfie decision paths are driven here through a stand-in face
engine: the thresholds and outcomes are covered, the models themselves are validated on real photos.
"""

from __future__ import annotations

from datetime import date

import numpy as np
import pytest
from helpers import make_ctx

from pehchaan.documents.classify import classify
from pehchaan.documents.parse import extract_fields
from pehchaan.domain.decision import decide
from pehchaan.domain.models import CaptureSource, CheckStatus, DocType, EvidenceLevel
from pehchaan.ocr.base import OcrLine, OcrResult
from pehchaan.pipeline.checks.selfie import SelfieCheck
from pehchaan.vision.faces import Face


def ocr(*texts: str) -> OcrResult:
    return OcrResult(
        lines=[OcrLine(t, 0.96, (0.1, 0.1 + i * 0.08, 0.7, 0.16 + i * 0.08)) for i, t in enumerate(texts)],
        provider="test",
    )


def selfie_bytes() -> bytes:
    import cv2

    ok, buffer = cv2.imencode(".jpg", np.full((240, 240, 3), 180, dtype=np.uint8))
    assert ok
    return buffer.tobytes()


class FakeFaceEngine:
    """Stands in for YuNet/SFace/MiniFASNet so selfie outcomes can be tested without real faces."""

    def __init__(self, *, found: bool = True, live: float = 0.9, similarity: float = 0.8) -> None:
        self._found = found
        self._live = live
        self._similarity = similarity

    def detect(self, image):
        return (
            [Face(np.array([10.0, 10.0, 100.0, 100.0] + [0.0] * 10 + [0.99], dtype=np.float32))] if self._found else []
        )

    def liveness(self, image, face) -> float:
        return self._live

    def embed(self, image, face):
        return np.ones(128, dtype=np.float32) / np.sqrt(128)

    def similarity(self, a, b) -> float:
        return self._similarity


def run_selfie(policy, engine, *, source: CaptureSource, reference: bool = True):
    """Build the check and a context carrying a selfie, ready to await."""
    ctx = make_ctx(policy)
    ctx.selfie = selfie_bytes()
    ctx.payload.capture.selfie_source = source
    if reference:
        ctx.id_face_embedding = np.ones(128, dtype=np.float32) / np.sqrt(128)
    return SelfieCheck(engine, liveness_enabled=True, liveness_threshold=0.5), ctx


async def test_live_selfie_that_matches_passes(policy):
    check, ctx = run_selfie(policy, FakeFaceEngine(), source=CaptureSource.CAMERA)
    result = await check.run(ctx)
    assert result.status is CheckStatus.PASS
    assert [f.code for f in result.findings] == ["SELFIE_MATCH"]


async def test_uploaded_selfie_matches_but_cannot_prove_presence(policy):
    """CEN/TS 18099: passing a face check says nothing about where the image came from."""
    check, ctx = run_selfie(policy, FakeFaceEngine(), source=CaptureSource.UPLOAD)
    result = await check.run(ctx)
    assert result.status is CheckStatus.WARN  # not PASS, so L4 stays out of reach
    assert {f.code for f in result.findings} == {"SELFIE_MATCH", "SELFIE_NOT_LIVE_CAPTURE"}


async def test_spoofed_selfie_asks_for_another_one(policy):
    check, ctx = run_selfie(policy, FakeFaceEngine(live=0.1), source=CaptureSource.CAMERA)
    result = await check.run(ctx)
    assert result.status is CheckStatus.FAIL
    assert [f.code for f in result.findings] == ["SELFIE_SPOOF_SUSPECTED"]


async def test_different_face_goes_to_review_never_rejection(policy):
    check, ctx = run_selfie(policy, FakeFaceEngine(similarity=0.05), source=CaptureSource.CAMERA)
    result = await check.run(ctx)
    assert result.status is CheckStatus.WARN
    assert [f.code for f in result.findings] == ["SELFIE_MISMATCH"]


async def test_no_face_in_the_selfie_asks_for_another_one(policy):
    check, ctx = run_selfie(policy, FakeFaceEngine(found=False), source=CaptureSource.CAMERA)
    result = await check.run(ctx)
    assert [f.code for f in result.findings] == ["SELFIE_NO_FACE"]


async def test_no_photo_on_the_document_to_compare_with(policy):
    check, ctx = run_selfie(policy, FakeFaceEngine(), source=CaptureSource.CAMERA, reference=False)
    result = await check.run(ctx)
    assert result.status is CheckStatus.SKIPPED
    assert [f.code for f in result.findings] == ["SELFIE_NO_REFERENCE"]


async def test_event_requiring_a_selfie_asks_for_one(policy):
    ctx = make_ctx(policy.model_copy(update={"require_selfie": True}))
    result = await SelfieCheck(FakeFaceEngine(), True, 0.5).run(ctx)
    assert result.status is CheckStatus.FAIL
    assert [f.code for f in result.findings] == ["SELFIE_REQUIRED"]


def test_a_live_matching_selfie_reaches_the_top_of_the_ladder(policy):
    from helpers import result as check_result

    ledger = [
        check_result("quality"),
        check_result("extract"),
        check_result("document_rules"),
        check_result("duplicates"),
        check_result("identity", CheckStatus.PASS, "NAME_MATCH"),
        check_result("aadhaar_qr", CheckStatus.PASS, "AADHAAR_QR_VERIFIED"),
        check_result("selfie", CheckStatus.PASS, "SELFIE_MATCH"),
    ]
    outcome = decide(ledger, policy)
    assert outcome.level is EvidenceLevel.PRESENT
    assert outcome.confidence == 0.98


# --- the other Indian documents ---------------------------------------------------------------


def test_passport_mrz_is_parsed_and_check_digits_validated():
    result = ocr(
        "REPUBLIC OF INDIA",
        "PASSPORT",
        "P<INDSHARMA<<SNEHA<<<<<<<<<<<<<<<<<<<<<<<<<<",
        "M8392571<7IND0304122F3201015<<<<<<<<<<<<<<08",
    )
    fields = extract_fields(result, classify(result.text)[0])
    assert fields.doc_type is DocType.PASSPORT
    assert fields.name == "SNEHA SHARMA"
    assert fields.id_number == "M8392571"
    assert fields.dob == date(2003, 4, 12)


def test_passport_with_a_broken_check_digit_yields_no_number():
    result = ocr(
        "REPUBLIC OF INDIA",
        "PASSPORT",
        "P<INDSHARMA<<SNEHA<<<<<<<<<<<<<<<<<<<<<<<<<<",
        "M8392571<1IND0304122F3201015<<<<<<<<<<<<<<08",  # passport-number check digit wrong
    )
    fields = extract_fields(result, classify(result.text)[0])
    assert fields.id_number is None


def test_voter_id_is_parsed():
    result = ocr(
        "ELECTION COMMISSION OF INDIA", "Elector's Name: Kavya Iyer", "ABC1234566", "Date of Birth: 09/08/2004"
    )
    fields = extract_fields(result, classify(result.text)[0])
    assert fields.doc_type is DocType.VOTER_ID
    assert (fields.name, fields.id_number, fields.dob) == ("Kavya Iyer", "ABC1234566", date(2004, 8, 9))


def test_driving_licence_is_parsed():
    result = ocr("DRIVING LICENCE", "Union of India", "DL No: KA05 20190001234", "Name: Rohan Nair", "DOB: 11/05/2001")
    fields = extract_fields(result, classify(result.text)[0])
    assert fields.doc_type is DocType.DRIVING_LICENCE
    assert fields.id_number == "KA05" + "2019" + "0001234"
    assert (fields.name, fields.dob) == ("Rohan Nair", date(2001, 5, 11))


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("GOVERNMENT OF INDIA 2341 2341 2346 DOB: 11/05/2004 MALE", DocType.AADHAAR),
        ("INCOME TAX DEPARTMENT Permanent Account Number ABCPR1234F", DocType.PAN),
        ("ELECTION COMMISSION OF INDIA Elector ABC1234566", DocType.VOTER_ID),
        ("REPUBLIC OF INDIA PASSPORT P<IND", DocType.PASSPORT),
        ("DRIVING LICENCE DL No TRANSPORT", DocType.DRIVING_LICENCE),
        ("R V College of Engineering STUDENT IDENTITY CARD Roll No: 1RV22CS042", DocType.COLLEGE_ID),
        ("a shopping receipt for two coffees", DocType.UNKNOWN),
    ],
)
def test_document_types_are_recognised(text, expected):
    assert classify(text)[0] is expected
