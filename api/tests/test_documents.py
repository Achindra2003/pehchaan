from __future__ import annotations

from datetime import date

import pytest
from cryptography.hazmat.primitives.asymmetric import rsa

from pehchaan.aadhaar import secure_qr
from pehchaan.aadhaar.secure_qr import CertificateStore
from pehchaan.documents.classify import classify
from pehchaan.documents.dates import parse_date
from pehchaan.documents.parse import extract_fields
from pehchaan.domain.models import DocType
from pehchaan.institutions import email_matches_institution
from pehchaan.names import APPROVE_AT, name_score
from pehchaan.ocr.base import OcrLine, OcrResult
from pehchaan.specimens import make_test_signing_key


def ocr(*texts: str) -> OcrResult:
    return OcrResult(
        lines=[OcrLine(t, 0.97, (0.1, 0.1 + i * 0.08, 0.6, 0.16 + i * 0.08)) for i, t in enumerate(texts)],
        provider="test",
    )


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("DOB: 11/05/2004", date(2004, 5, 11)),
        ("DOB:11-05-2004", date(2004, 5, 11)),
        ("Date of Birth 1O/O5/2OO4", date(2004, 5, 10)),
        ("12 Jan 2003", date(2003, 1, 12)),
        ("2004-05-11", date(2004, 5, 11)),
    ],
)
def test_dates(text, expected):
    assert parse_date(text) == expected


def test_month_year_validity_is_end_of_month():
    assert parse_date("Valid upto: 06/2027", month_year_ok=True) == date(2027, 6, 30)


def test_secure_qr_round_trip_and_signature(tmp_path):
    key = make_test_signing_key(tmp_path)
    payload = secure_qr.encode(
        name="Asha Rao", dob="11-05-2004", gender="F", reference_id="4821202501011200000", private_key=key
    )
    qr = secure_qr.decode(payload)
    assert (qr.name, qr.dob, qr.gender, qr.last4, qr.version) == ("Asha Rao", date(2004, 5, 11), "F", "4821", "V2")

    store = CertificateStore.load(tmp_path)
    assert store.verify(qr) == "test-uidai-NOT-REAL.pem"

    forged = secure_qr.encode(
        name="Asha Rao",
        dob="11-05-2004",
        gender="F",
        reference_id="4821202501011200000",
        private_key=rsa.generate_private_key(public_exponent=65537, key_size=2048),
    )
    assert store.verify(secure_qr.decode(forged)) is None


def test_legacy_xml_qr_is_marked_unsigned():
    qr = secure_qr.decode('<PrintLetterBarcodeData uid="234123412346" name="Asha Rao" yob="2004" gender="F"/>')
    assert qr.legacy_unsigned and qr.year_of_birth == 2004 and qr.last4 == "2346"


def test_aadhaar_front_parsing_with_glued_ocr_text():
    result = ocr("GOVERNMENTOFINDIA", "Asha Rao", "DOB:11/05/2004", "FEMALE", "234123412346")
    doc_type, _ = classify(result.text)
    fields = extract_fields(result, doc_type)
    assert doc_type is DocType.AADHAAR
    assert (fields.name, fields.dob, fields.gender, fields.id_number) == (
        "Asha Rao",
        date(2004, 5, 11),
        "F",
        "234123412346",
    )


def test_pan_parsing_repairs_ocr_character_swaps():
    result = ocr(
        "INCOME TAX DEPARTMENT",
        "GOVT. OF INDIA",
        "ABCPR1Z34F",
        "Name",
        "ASHA RAO",
        "Father's Name",
        "RAVI RAO",
        "11/05/2004",
    )
    fields = extract_fields(result, classify(result.text)[0])
    assert fields.doc_type is DocType.PAN
    assert (fields.id_number, fields.name, fields.dob) == ("ABCPR1234F", "ASHA RAO", date(2004, 5, 11))


def test_college_id_parsing():
    result = ocr(
        "R V College of Engineering",
        "STUDENT IDENTITY CARD",
        "Name: Kavya Iyer",
        "Roll No: 1RV22CS042",
        "Valid upto: 06/2027",
    )
    fields = extract_fields(result, classify(result.text)[0])
    assert fields.doc_type is DocType.COLLEGE_ID
    assert fields.institution == "R V College of Engineering"
    assert (fields.name, fields.id_number, fields.valid_until) == ("Kavya Iyer", "1RV22CS042", date(2027, 6, 30))


@pytest.mark.parametrize(
    ("a", "b"),
    [("Asha Rao", "ASHARAO"), ("Kumar Suresh", "Suresh Kumar"), ("Lakshmi Devi", "Laxmi Devi")],
)
def test_names_that_should_match(a, b):
    assert name_score(a, b) >= APPROVE_AT


def test_different_people_do_not_match():
    assert name_score("Asha Rao", "Rohit Verma") < 0.5


def test_college_email_domains():
    assert email_matches_institution("kavya@rvce.edu.in", "R V College of Engineering")
    assert not email_matches_institution("kavya@gmail.com", "R V College of Engineering")
