"""End to end on synthetic SPECIMEN cards: real OCR, real QR decoding, real signature checks."""

from __future__ import annotations

import json
import random
from datetime import date

import pytest
from conftest import API_KEY
from helpers import CONSENT

from pehchaan import specimens as sp

pytestmark = pytest.mark.e2e
EVENT = "ai-build-challenge-blr"
HEADERS = {"X-API-Key": API_KEY}


@pytest.fixture(scope="module")
def key(signing_dir):
    return sp.make_test_signing_key(signing_dir)


def submit(
    client,
    image: bytes,
    name: str,
    dob: date | str | None,
    registration: str,
    event: str = EVENT,
    subject: str | None = None,
) -> dict:
    form = {"name": name, **({"dob": str(dob)} if dob else {})}
    body = {"registration_id": registration, "event_id": event, "form": form, "consent": CONSENT, "subject_id": subject}
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


def test_verified_participant_reuses_a_pass_at_the_next_event(ocr_client, key):
    rng = random.Random(7)
    person = sp.make_person(rng, dob=date(2002, 2, 2))
    photo = sp.photograph(sp.render_aadhaar(person, qr_payload=sp.secure_qr_for(person, key)), rng)
    first = submit(ocr_client, photo, person.name, person.dob, "e2e-pass-first", subject="hackingly-user-77")
    assert first["decision"] == "verified"
    issued = first["pehchaan_pass"]
    assert issued["level"] == 3
    stored = ocr_client.get(f"/v1/verifications/{first['verification_id']}", headers=HEADERS).json()
    assert stored["pehchaan_pass"] is None  # returned once, never stored

    reuse = {
        "registration_id": "e2e-pass-second",
        "event_id": "junior-coders-13-17",
        "form": {"name": person.name, "dob": str(person.dob)},
        "consent": CONSENT,
        "subject_id": "hackingly-user-77",
        "pass_token": issued["token"],
    }
    second = ocr_client.post("/v1/verifications/pass", json=reuse, headers=HEADERS).json()
    assert second["evidence_source"] == "pass"
    assert second["decision"] == "not_eligible"  # 24 at a 13-17 event: the pass carries the signed DOB
    assert second["usage"]["textract_detect_pages"] == 0

    adult = {**reuse, "registration_id": "e2e-pass-third", "event_id": EVENT}
    third = ocr_client.post("/v1/verifications/pass", json=adult, headers=HEADERS).json()
    assert third["decision"] == "verified" and third["evidence_level"] == 3

    stolen = {**adult, "registration_id": "e2e-pass-stolen", "subject_id": "someone-else"}
    assert "PASS_SUBJECT_MISMATCH" in codes(
        ocr_client.post("/v1/verifications/pass", json=stolen, headers=HEADERS).json()
    )


def test_pass_is_revoked_when_fraud_is_found_later(ocr_client, key):
    rng = random.Random(8)
    owner = sp.make_person(rng)
    card = sp.render_aadhaar(owner, qr_payload=sp.secure_qr_for(owner, key))
    first = submit(
        ocr_client, sp.photograph(card, rng), owner.name, owner.dob, "e2e-revoke-owner", subject="user-owner"
    )
    token = first["pehchaan_pass"]["token"]
    submit(ocr_client, sp.photograph(card, rng), "Farhan Ali", owner.dob, "e2e-revoke-impostor")

    reuse = {
        "registration_id": "e2e-revoke-reuse",
        "event_id": EVENT,
        "form": {"name": owner.name, "dob": str(owner.dob)},
        "consent": CONSENT,
        "subject_id": "user-owner",
        "pass_token": token,
    }
    result = ocr_client.post("/v1/verifications/pass", json=reuse, headers=HEADERS).json()
    assert result["decision"] == "needs_review"
    assert "PASS_REVOKED" in codes(result)
