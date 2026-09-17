"""End to end on synthetic SPECIMEN cards: real OCR, real QR decoding, real signature checks."""

from __future__ import annotations

import json
import random
from datetime import date

import pytest
from conftest import API_KEY

from pehchaan import specimens as sp

pytestmark = pytest.mark.e2e
EVENT = "ai-build-challenge-blr"


@pytest.fixture(scope="module")
def key(signing_dir):
    return sp.make_test_signing_key(signing_dir)


def submit(client, image: bytes, name: str, dob: date | str | None, registration: str, event: str = EVENT) -> dict:
    form = {"name": name, **({"dob": str(dob)} if dob else {})}
    body = {"registration_id": registration, "event_id": event, "form": form}
    response = client.post(
        "/v1/verifications",
        data={"payload": json.dumps(body)},
        files={"id_image": ("id.jpg", image, "image/jpeg")},
        headers={"X-API-Key": API_KEY},
    )
    assert response.status_code == 200, response.text
    return response.json()


def codes(result: dict) -> set[str]:
    return {reason["code"] for reason in result["reasons"]}


def test_genuine_aadhaar_is_verified_by_signature(ocr_client, key):
    rng = random.Random(1)
    person = sp.make_person(rng, dob=date(2003, 4, 12))
    photo = sp.photograph(sp.render_aadhaar(person, qr_payload=sp.secure_qr_for(person, key)), rng)
    result = submit(ocr_client, photo, person.name, person.dob, "e2e-genuine")
    assert result["decision"] == "verified"
    assert result["evidence_level"] == 3
    assert result["document"] == {"type": "aadhaar", "id_last4": person.aadhaar[-4:], "age_on_event_date": 23}


def test_edited_dob_is_contradicted_by_signed_qr(ocr_client, key):
    rng = random.Random(2)
    minor = sp.make_person(rng, dob=date(2010, 3, 5))
    card = sp.render_aadhaar(minor, qr_payload=sp.secure_qr_for(minor, key))
    edited = sp.paste_edit(card, (290, 212, 640, 262), "DOB: 05/03/2004", 36)
    result = submit(ocr_client, sp.photograph(edited, rng), minor.name, "2004-03-05", "e2e-edited")
    assert result["decision"] == "not_eligible"
    assert "AADHAAR_PRINT_CONTRADICTS_QR" in codes(result)


def test_aadhaar_without_qr_asks_once_then_goes_to_review(ocr_client):
    rng = random.Random(3)
    person = sp.make_person(rng)
    photo = sp.photograph(sp.render_aadhaar(person, qr_payload=None), rng)
    first = submit(ocr_client, photo, person.name, person.dob, "e2e-noqr")
    assert first["decision"] == "action_required"
    second = submit(ocr_client, photo, person.name, person.dob, "e2e-noqr")
    assert second["decision"] == "needs_review"
    assert "AADHAAR_QR_MISSING_AFTER_RETAKE" in codes(second)


def test_reused_id_flags_both_registrations(ocr_client, key):
    rng = random.Random(4)
    owner = sp.make_person(rng)
    card = sp.render_aadhaar(owner, qr_payload=sp.secure_qr_for(owner, key))
    first = submit(ocr_client, sp.photograph(card, rng), owner.name, owner.dob, "e2e-owner")
    assert first["decision"] == "verified"

    second = submit(ocr_client, sp.photograph(card, rng), "Rohit Verma", owner.dob, "e2e-impostor")
    assert second["decision"] == "needs_review"
    assert "DUPLICATE_ID_OTHER_IDENTITY" in codes(second)

    earlier = ocr_client.get(f"/v1/verifications/{first['verification_id']}", headers={"X-API-Key": API_KEY}).json()
    assert earlier["decision"] == "needs_review"
    assert earlier["flags"]["duplicate_suspected"]


def test_blurry_photo_asks_for_retake(ocr_client, key):
    rng = random.Random(5)
    person = sp.make_person(rng)
    photo = sp.photograph(sp.render_aadhaar(person, qr_payload=sp.secure_qr_for(person, key)), rng, blur=4)
    result = submit(ocr_client, photo, person.name, person.dob, "e2e-blurry")
    assert result["decision"] == "action_required"
    assert result["actions"] == ["retake_id_photo"]


def test_student_event_accepts_current_college_id(ocr_client):
    rng = random.Random(6)
    student = sp.make_person(rng, dob=date(2004, 8, 9))
    card = sp.render_college_id(
        student, institution="Specimen Institute of Technology", roll="1SI22CS042", valid_until=date(2027, 6, 30)
    )
    result = submit(
        ocr_client, sp.photograph(card, rng), student.name, student.dob, "e2e-student", "campus-hack-students"
    )
    assert result["decision"] == "verified"
    assert result["document"]["type"] == "college_id"
