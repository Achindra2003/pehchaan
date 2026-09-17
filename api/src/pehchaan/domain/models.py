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
    QR_SIGNED = "qr_signed"  # UIDAI Secure QR, signature verified
    AADHAAR_VC = "aadhaar_vc"  # Aadhaar App verifiable credential, signature verified
    VISION_MODEL = "vision_model"


SIGNED_SOURCES = frozenset({FieldSource.QR_SIGNED, FieldSource.AADHAAR_VC})


class EvidenceSource(StrEnum):
    DOCUMENT = "document"  # photo or PDF of an ID
    PASS = "pass"  # noqa: S105 - Pehchaan Pass from an earlier verification
    AADHAAR_APP = "aadhaar_app"  # OpenID4VP presentation from the Aadhaar App


# --- Inputs -----------------------------------------------------------------


class RegistrationForm(BaseModel):
    name: str
    dob: date | None = None
    email: str | None = None
    email_verified: bool = False  # Hackingly confirmed control of this address (OTP/link)
    phone: str | None = None
    institution: str | None = None


class CaptureSource(StrEnum):
    CAMERA = "camera"  # captured live in the browser
    UPLOAD = "upload"
    UNKNOWN = "unknown"


class Capture(BaseModel):
    id_source: CaptureSource = CaptureSource.UNKNOWN
    selfie_source: CaptureSource = CaptureSource.UNKNOWN


class Consent(BaseModel):
    """DPDP notice and consent captured by Hackingly before the ID is uploaded."""

    accepted: bool
    notice_version: str = Field(min_length=1, max_length=40)
    accepted_at: datetime


class RegistrationBase(BaseModel):
    registration_id: str = Field(min_length=1, max_length=128)
    event_id: str = Field(min_length=1, max_length=128)
    form: RegistrationForm
    consent: Consent | None = None
    subject_id: str | None = Field(
        default=None, max_length=128, description="Hackingly account id; enables Pehchaan Pass issue and reuse"
    )


class VerificationPayload(RegistrationBase):
    capture: Capture = Field(default_factory=Capture)
    device_id: str | None = Field(default=None, max_length=128, description="e.g. FingerprintJS visitorId")
    textract_response: dict[str, Any] | None = None


class PassVerificationRequest(RegistrationBase):
    pass_token: str = Field(min_length=20, max_length=4096)


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
    age_attestations: dict[int, bool] = Field(default_factory=dict)  # e.g. {18: True} from AgeAbove18
    confidence: dict[str, float] = Field(default_factory=dict)
    boxes: dict[str, tuple[float, float, float, float]] = Field(default_factory=dict, exclude=True, repr=False)

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


class ReviewAction(StrEnum):
    APPROVE = "approve"
    REJECT = "reject"
    REQUEST_RETAKE = "request_retake"


REVIEW_DECISIONS = {
    ReviewAction.APPROVE: Decision.VERIFIED,
    ReviewAction.REJECT: Decision.NOT_ELIGIBLE,
    ReviewAction.REQUEST_RETAKE: Decision.ACTION_REQUIRED,
}


class ReviewRequest(BaseModel):
    action: ReviewAction
    reviewer: str = Field(min_length=1, max_length=80)
    note: str = Field(default="", max_length=500)


class ReviewRecord(ReviewRequest):
    reviewed_at: datetime


class OutcomeRequest(BaseModel):
    """What Hackingly's existing process decided, recorded while an event runs in shadow mode."""

    decision: Decision
    source: str = Field(default="manual_check", max_length=40)


class ObservedOutcome(OutcomeRequest):
    recorded_at: datetime


class Usage(BaseModel):
    """Metered per verification: the basis for cost per verification and billing."""

    ocr_provider: str | None = None
    textract_detect_pages: int = 0
    textract_query_pages: int = 0
    compute_ms: int = 0
    estimated_cost_usd: float = 0.0


class PassIssued(BaseModel):
    pass_id: str
    token: str
    level: EvidenceLevel
    expires_at: datetime


class VerificationResult(BaseModel):
    verification_id: str
    registration_id: str
    event_id: str
    decision: Decision  # current decision; a reviewer may have changed it
    automated_decision: Decision
    enforced: bool = True  # False while the event runs in shadow mode
    confidence: float
    evidence_level: EvidenceLevel
    evidence_source: EvidenceSource = EvidenceSource.DOCUMENT
    reasons: list[Reason]
    actions: list[Action]
    flags: Flags
    document: DocumentSummary
    policy_version: str
    checks: list[CheckResult]
    review: ReviewRecord | None = None
    observed_outcome: ObservedOutcome | None = None
    consent_notice: str | None = None
    usage: Usage = Field(default_factory=Usage)
    pehchaan_pass: PassIssued | None = None  # returned once, never stored
    latency_ms: int = 0
    erased_at: datetime | None = None
    created_at: datetime


class VerificationSummary(BaseModel):
    verification_id: str
    registration_id: str
    event_id: str
    decision: Decision
    automated_decision: Decision
    confidence: float
    evidence_level: EvidenceLevel
    flags: Flags
    document: DocumentSummary
    evidence_source: EvidenceSource
    enforced: bool
    reviewed: bool
    priority: int  # higher first in the review queue
    top_reason: str | None
    created_at: datetime


class Job(BaseModel):
    job_id: str
    status: str  # queued, running, done, failed
    verification_id: str | None = None
    error: str | None = None
