from __future__ import annotations

from datetime import date

import pytest
from helpers import make_ctx

from pehchaan.domain.models import CheckStatus, DocType, FieldSource
from pehchaan.pipeline.checks.document_rules import DocumentRulesCheck
from pehchaan.pipeline.checks.eligibility import EligibilityCheck, age_on


def codes(result):
    return [f.code for f in result.findings]


@pytest.mark.parametrize(
    ("dob", "expected"),
    [(date(2008, 9, 18), 18), (date(2008, 9, 19), 17), (date(2004, 2, 29), 22)],
)
def test_age_is_computed_on_event_date(dob, expected):
    assert age_on(dob, date(2026, 9, 18)) == expected


async def test_underage_with_signed_dob_is_hard_evidence(policy):
    ctx = make_ctx(policy, doc_type=DocType.AADHAAR, dob=date(2010, 1, 1), dob_source=FieldSource.QR_SIGNED)
    result = await EligibilityCheck().run(ctx)
    assert result.status is CheckStatus.FAIL
    assert "AGE_BELOW_MIN_CONFIRMED" in codes(result)


async def test_underage_from_unconfirmed_ocr_goes_to_review(policy):
    ctx = make_ctx(
        policy,
        form_dob=date(2004, 1, 1),
        doc_type=DocType.PAN,
        dob=date(2010, 1, 1),
        dob_source=FieldSource.OCR,
        confidence={"dob": 0.97},
    )
    result = await EligibilityCheck().run(ctx)
    assert result.status is CheckStatus.PASS
    assert "AGE_OUT_OF_RANGE_UNCONFIRMED" in codes(result)


async def test_confident_ocr_matching_form_is_hard_evidence(policy):
    dob = date(2010, 1, 1)
    ctx = make_ctx(
        policy, form_dob=dob, doc_type=DocType.PAN, dob=dob, dob_source=FieldSource.OCR, confidence={"dob": 0.95}
    )
    assert "AGE_BELOW_MIN_CONFIRMED" in codes(await EligibilityCheck().run(ctx))


async def test_year_of_birth_straddling_the_limit_is_uncertain(policy):
    ctx = make_ctx(policy, doc_type=DocType.AADHAAR, year_of_birth=2008)  # 17 or 18 on the event date
    assert "AGE_BOUNDARY_UNCERTAIN" in codes(await EligibilityCheck().run(ctx))


async def test_student_only_event_asks_aadhaar_holders_for_college_id(policy):
    ctx = make_ctx(policy.model_copy(update={"student_only": True}), doc_type=DocType.AADHAAR, dob=date(2004, 1, 1))
    assert "STUDENT_PROOF_REQUIRED" in codes(await EligibilityCheck().run(ctx))


async def test_expired_college_id_asks_for_current_one(policy):
    ctx = make_ctx(
        policy.model_copy(update={"student_only": True, "min_age": None}),
        doc_type=DocType.COLLEGE_ID,
        valid_until=date(2026, 6, 30),
    )
    assert "COLLEGE_ID_EXPIRED" in codes(await EligibilityCheck().run(ctx))


@pytest.mark.parametrize(
    ("doc_type", "number", "expected"),
    [
        (DocType.AADHAAR, "2341 2341 2346", "ID_NUMBER_VALID"),
        (DocType.AADHAAR, "2341 2341 2347", "ID_NUMBER_INVALID"),
        (DocType.AADHAAR, "XXXX XXXX 2346", "ID_NUMBER_MASKED"),
        (DocType.PAN, "ABCPR1234F", "ID_NUMBER_VALID"),
        (DocType.PAN, "ABCFR1234F", "PAN_NOT_INDIVIDUAL"),
    ],
)
async def test_document_number_rules(policy, doc_type, number, expected):
    ctx = make_ctx(policy, doc_type=doc_type, id_number=number, name="Asha Rao")
    assert expected in codes(await DocumentRulesCheck().run(ctx))


async def test_pan_surname_letter_only_lowers_confidence(policy):
    # Initial-first names ("R. Karthik") often break the PAN surname rule.
    ctx = make_ctx(policy, doc_type=DocType.PAN, id_number="ABCPS1234F", name="R Karthik")
    result = await DocumentRulesCheck().run(ctx)
    assert result.status is CheckStatus.PASS
    assert "PAN_SURNAME_INITIAL_MISMATCH" in codes(result)
