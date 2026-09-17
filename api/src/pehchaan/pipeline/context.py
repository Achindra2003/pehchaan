from __future__ import annotations

from dataclasses import dataclass, field

from pehchaan.domain.models import CheckResult, ExtractedFields, VerificationPayload
from pehchaan.domain.policy import EventPolicy


@dataclass
class VerificationContext:
    """Everything a check may read. Checks write only their own CheckResult,
    except `extract`, which fills `fields`, and `aadhaar_qr`, which may upgrade them."""

    payload: VerificationPayload
    policy: EventPolicy
    id_image: bytes
    id_media_type: str
    selfie: bytes | None = None
    fields: ExtractedFields = field(default_factory=ExtractedFields)
    results: dict[str, CheckResult] = field(default_factory=dict)
