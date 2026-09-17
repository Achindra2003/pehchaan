"""Contracts shared by the API, the pipeline and the decision engine."""

from __future__ import annotations

from datetime import date, datetime
from enum import IntEnum, StrEnum
from typing import Any

from pydantic import BaseModel, Field


class DocType(StrEnum):
    AADHAAR = "aadhaar"
    PAN = "pan"
    VOTER_ID = "voter_id"
    PASSPORT = "passport"
    DRIVING_LICENCE = "driving_licence"
    COLLEGE_ID = "college_id"
    UNKNOWN = "unknown"


class EvidenceLevel(IntEnum):
    UNUSABLE = 0
    READ = 1
    CONSISTENT = 2
    PROVEN = 3
    PRESENT = 4


class Decision(StrEnum):
    VERIFIED = "verified"
    NEEDS_REVIEW = "needs_review"
    ACTION_REQUIRED = "action_required"
    NOT_ELIGIBLE = "not_eligible"


class CheckStatus(StrEnum):
    PASS = "pass"  # noqa: S105 - a check status, not a password
    WARN = "warn"
    FAIL = "fail"
    SKIPPED = "skipped"
    ERROR = "error"


class Effect(StrEnum):
    """What a finding does to the decision. Ordered from weakest to strongest."""

    INFO = "info"
    PENALTY = "penalty"
    REVIEW = "review"
    ACTION = "action"
    REJECT = "reject"


class Action(StrEnum):
    RETAKE_ID_PHOTO = "retake_id_photo"
    USE_ORIGINAL_DOCUMENT = "use_original_document"
    UPLOAD_ACCEPTED_DOCUMENT = "upload_accepted_document"
    UPLOAD_COLLEGE_ID = "upload_college_id"
    RETAKE_SELFIE = "retake_selfie"


class FieldSource(StrEnum):
    FORM = "form"
    OCR = "ocr"
    QR_SIGNED = "qr_signed"
    VISION_MODEL = "vision_model"


# --- Inputs -----------------------------------------------------------------


class RegistrationForm(BaseModel):
    name: str
    dob: date | None = None
    email: str | None = None
    phone: str | None = None
    institution: str | None = None


class VerificationPayload(BaseModel):
    registration_id: str = Field(min_length=1, max_length=128)
    event_id: str = Field(min_length=1, max_length=128)
    form: RegistrationForm
    textract_response: dict[str, Any] | None = None


# --- Pipeline state ---------------------------------------------------------


class ExtractedFields(BaseModel):
    """What the pipeline has read off the document. Lives in memory only."""

    doc_type: DocType = DocType.UNKNOWN
    name: str | None = None
    dob: date | None = None
    year_of_birth: int | None = None
    gender: str | None = None
    id_number: str | None = Field(default=None, exclude=True, repr=False)
    institution: str | None = None
    valid_until: date | None = None
    dob_source: FieldSource | None = None
    confidence: dict[str, float] = Field(default_factory=dict)

    @property
    def id_last4(self) -> str | None:
        if not self.id_number:
            return None
        digits = "".join(ch for ch in self.id_number if ch.isalnum())
        return digits[-4:] or None


class Finding(BaseModel):
    code: str
    params: dict[str, str | int | float] = Field(default_factory=dict)


class CheckResult(BaseModel):
    check: str
    status: CheckStatus
    findings: list[Finding] = Field(default_factory=list)
    duration_ms: int = 0
    details: dict[str, Any] = Field(default_factory=dict)


# --- Outputs ----------------------------------------------------------------


class Reason(BaseModel):
    code: str
    effect: Effect
    check: str
    message: str


class Flags(BaseModel):
    minor: bool = False
    guardian_consent_required: bool = False
    duplicate_suspected: bool = False


class DocumentSummary(BaseModel):
    type: DocType = DocType.UNKNOWN
    id_last4: str | None = None
    age_on_event_date: int | None = None


class VerificationResult(BaseModel):
    verification_id: str
    registration_id: str
    event_id: str
    decision: Decision
    confidence: float
    evidence_level: EvidenceLevel
    reasons: list[Reason]
    actions: list[Action]
    flags: Flags
    document: DocumentSummary
    policy_version: str
    checks: list[CheckResult]
    created_at: datetime
