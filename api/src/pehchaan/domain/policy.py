"""Per-event eligibility rules, set by the organiser and versioned."""

from __future__ import annotations

from datetime import date

from pydantic import BaseModel, Field, model_validator

from pehchaan.domain.models import DocType, EvidenceLevel

ALL_DOCUMENTS = frozenset(DocType) - {DocType.UNKNOWN}


class EventRules(BaseModel):
    """What the organiser sets. The service assigns event_id and version."""

    event_date: date
    min_age: int | None = Field(default=None, ge=0, le=120)
    max_age: int | None = Field(default=None, ge=0, le=120)
    student_only: bool = False
    accepted_documents: frozenset[DocType] = ALL_DOCUMENTS
    require_selfie: bool = False
    auto_verify_min_level: EvidenceLevel = EvidenceLevel.CONSISTENT
    # With an age rule, an Aadhaar is only trusted for its DOB when its signed QR is readable.
    require_aadhaar_qr: bool = True
    guardian_consent_under: int = 18

    @model_validator(mode="after")
    def _check_age_window(self) -> EventRules:
        if self.min_age is not None and self.max_age is not None and self.min_age > self.max_age:
            raise ValueError("min_age must not exceed max_age")
        return self


class EventPolicy(EventRules):
    event_id: str
    version: int = 1

    @property
    def version_tag(self) -> str:
        return f"{self.event_id}@{self.version}"
