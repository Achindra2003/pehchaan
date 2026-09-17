from __future__ import annotations

from datetime import date

from pehchaan.domain.models import (
    CheckResult,
    CheckStatus,
    ExtractedFields,
    RegistrationForm,
    VerificationPayload,
)
from pehchaan.domain.policy import EventPolicy
from pehchaan.pipeline.checks.base import finding
from pehchaan.pipeline.context import VerificationContext

EVENT_DATE = date(2026, 9, 18)
CONSENT = {"accepted": True, "notice_version": "hackingly-idv-2026-09", "accepted_at": "2026-09-17T10:00:00Z"}


def make_ctx(
    policy: EventPolicy, form_dob: date | None = None, form_name: str = "Asha Rao", **fields: object
) -> VerificationContext:
    payload = VerificationPayload(
        registration_id="reg_1",
        event_id=policy.event_id,
        form=RegistrationForm(name=form_name, dob=form_dob),
    )
    return VerificationContext(
        payload=payload,
        policy=policy,
        id_image=b"",
        id_media_type="image/jpeg",
        fields=ExtractedFields(**fields),
    )


def result(check: str, status: CheckStatus = CheckStatus.PASS, *codes: str, **params: str | int) -> CheckResult:
    return CheckResult(check=check, status=status, findings=[finding(code, **params) for code in codes])


def consistent_ledger() -> list[CheckResult]:
    """Evidence for a clean L2 registration."""
    return [
        result("quality"),
        result("extract"),
        result("document_rules"),
        result("duplicates"),
        result("identity", CheckStatus.PASS, "NAME_MATCH"),
    ]
