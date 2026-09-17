from __future__ import annotations

from helpers import consistent_ledger, result

from pehchaan.domain.decision import decide
from pehchaan.domain.models import Action, CheckStatus, Decision, EvidenceLevel
from pehchaan.domain.reasons import CATALOG


def test_consistent_evidence_is_verified_at_l2(policy):
    outcome = decide(consistent_ledger(), policy)
    assert outcome.decision is Decision.VERIFIED
    assert outcome.level is EvidenceLevel.CONSISTENT
    assert outcome.confidence == 0.85


def test_signed_qr_raises_level_and_confidence(policy):
    ledger = [*consistent_ledger(), result("aadhaar_qr", CheckStatus.PASS, "AADHAAR_QR_VERIFIED")]
    outcome = decide(ledger, policy)
    assert outcome.level is EvidenceLevel.PROVEN
    assert outcome.confidence == 0.95


def test_levels_are_cumulative(policy):
    # A selfie match without L3 proof does not reach L4.
    ledger = [*consistent_ledger(), result("selfie", CheckStatus.PASS, "SELFIE_MATCH")]
    outcome = decide(ledger, policy)
    assert outcome.level is EvidenceLevel.CONSISTENT
    assert outcome.confidence == 0.89


def test_blurry_image_asks_for_retake_not_rejection(policy):
    outcome = decide([result("quality", CheckStatus.FAIL, "IMAGE_BLURRY")], policy)
    assert outcome.decision is Decision.ACTION_REQUIRED
    assert outcome.level is EvidenceLevel.UNUSABLE
    assert outcome.actions == [Action.RETAKE_ID_PHOTO]


def test_hard_evidence_beats_everything(policy):
    ledger = [
        *consistent_ledger(),
        result("selfie", CheckStatus.WARN, "SELFIE_SPOOF_SUSPECTED"),
        result("eligibility", CheckStatus.FAIL, "AGE_BELOW_MIN_CONFIRMED", age=16, min_age=18),
    ]
    outcome = decide(ledger, policy)
    assert outcome.decision is Decision.NOT_ELIGIBLE
    assert outcome.actions == []
    assert "Age 16 on the event date is below this event's minimum of 18." in [r.message for r in outcome.reasons]


def test_crashed_check_goes_to_review_never_rejection(policy):
    ledger = [*consistent_ledger(), result("tamper", CheckStatus.ERROR)]
    outcome = decide(ledger, policy)
    assert outcome.decision is Decision.NEEDS_REVIEW
    assert [r.code for r in outcome.reasons if r.check == "tamper"] == ["CHECK_ERROR"]


def test_duplicate_goes_to_review_and_sets_flag(policy):
    ledger = [*consistent_ledger(), result("duplicates", CheckStatus.WARN, "DUPLICATE_ID_OTHER_IDENTITY")]
    outcome = decide(ledger, policy)
    assert outcome.decision is Decision.NEEDS_REVIEW
    assert outcome.flags.duplicate_suspected


def test_insufficient_evidence_is_reviewed(policy):
    outcome = decide([result("quality"), result("extract")], policy)
    assert outcome.decision is Decision.NEEDS_REVIEW
    assert "LEVEL_BELOW_EVENT_MINIMUM" in [r.code for r in outcome.reasons]


def test_minor_flags_guardian_consent_without_blocking(policy):
    ledger = [*consistent_ledger(), result("eligibility", CheckStatus.PASS, "MINOR_GUARDIAN_CONSENT", under=18)]
    outcome = decide(ledger, policy.model_copy(update={"min_age": None}))
    assert outcome.decision is Decision.VERIFIED
    assert outcome.flags.minor and outcome.flags.guardian_consent_required


def test_catalog_is_consistent():
    for code, spec in CATALOG.items():
        assert code.isupper(), code
        assert (spec.strength > 0) == (spec.effect.value == "reject"), code
