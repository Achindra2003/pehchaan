"""The problem statement's first requirement: build on Hackingly's existing Textract pipeline.

These run with `ocr_provider="none"`, so nothing can read the document except the Textract response
Hackingly sends with the registration.
"""

from __future__ import annotations

import json
import random
from datetime import date
from typing import Any

from conftest import API_KEY
from helpers import CONSENT

from pehchaan import specimens as sp
from pehchaan.documents.classify import classify
from pehchaan.documents.parse import extract_fields
from pehchaan.domain.models import DocType
from pehchaan.ocr.textract import parse_textract

HEADERS = {"X-API-Key": API_KEY}


def textract_response(lines: list[str], queries: dict[str, str] | None = None) -> dict[str, Any]:
    """A response shaped like DetectDocumentText / AnalyzeDocument, as Hackingly's pipeline returns it."""
    blocks: list[dict[str, Any]] = [{"BlockType": "PAGE", "Id": "page-1"}]
    for i, text in enumerate(lines):
        blocks.append(
            {
                "BlockType": "LINE",
                "Id": f"line-{i}",
                "Text": text,
                "Confidence": 99.1,
                "Geometry": {"BoundingBox": {"Left": 0.1, "Top": 0.1 + i * 0.08, "Width": 0.5, "Height": 0.05}},
            }
        )
    for alias, answer in (queries or {}).items():
        blocks.append(
            {
                "BlockType": "QUERY",
                "Id": f"query-{alias}",
                "Query": {"Text": f"What is the {alias}?", "Alias": alias},
                "Relationships": [{"Type": "ANSWER", "Ids": [f"answer-{alias}"]}],
            }
        )
        blocks.append(
            {
                "BlockType": "QUERY_RESULT",
                "Id": f"answer-{alias}",
                "Text": answer,
                "Confidence": 97.0,
                "Geometry": {"BoundingBox": {"Left": 0.4, "Top": 0.4, "Width": 0.3, "Height": 0.04}},
            }
        )
    return {"DocumentMetadata": {"Pages": 1}, "Blocks": blocks, "JobStatus": "SUCCEEDED"}


def test_textract_lines_and_queries_are_parsed():
    response = textract_response(
        ["GOVERNMENT OF INDIA", "Asha Rao", "DOB: 11/05/2004", "FEMALE", "2341 2341 2346"],
        queries={"ID_NUMBER": "2341 2341 2346"},
    )
    result = parse_textract(response)
    assert [line.text for line in result.lines][:2] == ["GOVERNMENT OF INDIA", "Asha Rao"]
    assert result.lines[0].confidence == 0.991
    assert result.queries["ID_NUMBER"].text == "2341 2341 2346"

    fields = extract_fields(result, classify(result.text)[0])
    assert fields.doc_type is DocType.AADHAAR
    assert (fields.name, fields.dob, fields.id_number) == ("Asha Rao", date(2004, 5, 11), "234123412346")


def test_pan_queries_fill_fields_the_lines_missed():
    response = textract_response(
        ["INCOME TAX DEPARTMENT", "GOVT. OF INDIA", "Permanent Account Number"],
        queries={"NAME": "Kavya Iyer", "DOB": "09/08/2004", "ID_NUMBER": "ABCPI1234F"},
    )
    result = parse_textract(response)
    fields = extract_fields(result, classify(result.text)[0])
    assert (fields.name, fields.dob, fields.id_number) == ("Kavya Iyer", date(2004, 8, 9), "ABCPI1234F")


def test_verification_runs_on_hackinglys_textract_output_without_any_ocr(client, signing_dir):
    """No OCR engine is configured: if this verifies, the reading came from their pipeline."""
    rng = random.Random(11)
    person = sp.make_person(rng, dob=date(2003, 4, 12))
    key = sp.make_test_signing_key(signing_dir)
    photo = sp.photograph(sp.render_aadhaar(person, qr_payload=sp.secure_qr_for(person, key)), rng)

    payload = {
        "registration_id": "textract-1",
        "event_id": "ai-build-challenge-blr",
        "form": {"name": person.name, "dob": str(person.dob)},
        "consent": CONSENT,
        "textract_response": textract_response(
            [
                "GOVERNMENT OF INDIA",
                person.name,
                f"DOB: {person.dob.strftime('%d/%m/%Y')}",
                person.gender_word,
                f"{person.aadhaar[:4]} {person.aadhaar[4:8]} {person.aadhaar[8:]}",
            ]
        ),
    }
    response = client.post(
        "/v1/verifications",
        data={"payload": json.dumps(payload)},
        files={"id_image": ("id.jpg", photo, "image/jpeg")},
        headers=HEADERS,
    )
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["decision"] == "verified"
    assert result["evidence_level"] == 3  # their OCR plus our signature check
    assert result["usage"]["ocr_provider"] == "textract:hackingly"
    assert result["usage"]["textract_detect_pages"] == 0  # we didn't call Textract again
    assert result["usage"]["estimated_cost_usd"] < 0.001


class StubTextract:
    """Stands in for the AWS client: the Queries path is exercised without credentials."""

    def __init__(self) -> None:
        self.detect_calls = 0
        self.query_calls: list[list[str]] = []

    def detect(self, jpeg: bytes):
        self.detect_calls += 1
        return parse_textract(
            textract_response(["INCOME TAX DEPARTMENT", "GOVT. OF INDIA", "Permanent Account Number"])
        )

    def query(self, jpeg: bytes, aliases: list[str]):
        self.query_calls.append(aliases)
        answers = {"NAME": "Kavya Iyer", "DOB": "09/08/2004", "ID_NUMBER": "ABCPI1234F"}
        return parse_textract(textract_response([], {a: answers[a] for a in aliases if a in answers})).queries


async def test_queries_are_asked_only_for_the_fields_the_lines_missed(signing_dir):
    """Textract Queries cost ten times a plain read, so they run only when something is actually missing."""
    import numpy as np
    from helpers import make_ctx

    from pehchaan.aadhaar.secure_qr import CertificateStore
    from pehchaan.pipeline.checks.extract import ExtractCheck
    from pehchaan.vision.qr import QrReader

    stub = StubTextract()
    check = ExtractCheck(QrReader(signing_dir), CertificateStore([]), stub, rapid=None, use_queries=True)
    ctx = make_ctx(policy_for_pan())
    ctx.image = np.full((400, 700, 3), 240, dtype=np.uint8)

    result = await check.run(ctx)
    assert stub.detect_calls == 1
    assert sorted(stub.query_calls[0]) == ["DOB", "ID_NUMBER", "NAME"]
    assert ctx.fields.name == "Kavya Iyer"
    assert ctx.fields.id_number == "ABCPI1234F"
    assert result.details["textract_query_pages"] == 1


def policy_for_pan():
    from datetime import date as _date

    from pehchaan.domain.policy import EventPolicy

    return EventPolicy(event_id="evt", event_date=_date(2026, 9, 18), min_age=18)
