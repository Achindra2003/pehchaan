from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from pehchaan.aadhaar.secure_qr import SecureQrData
from pehchaan.domain.models import CheckResult, ExtractedFields, VerificationPayload
from pehchaan.domain.policy import EventPolicy
from pehchaan.ocr.base import OcrResult
from pehchaan.vision.faces import Face


@dataclass
class IndexKeys:
    """What the duplicate index stores for this verification once a decision is made."""

    id_hashes: list[str] = field(default_factory=list)
    pdq: str | None = None
    face: np.ndarray | None = None
    device_hash: str | None = None


@dataclass
class VerificationContext:
    """Everything a check may read. Checks write their own CheckResult plus the shared
    artefacts documented below; raw document data here never leaves memory."""

    payload: VerificationPayload
    policy: EventPolicy
    id_image: bytes
    id_media_type: str
    selfie: bytes | None = None
    previous_attempts: int = 0  # earlier verifications for this registration

    image: np.ndarray | None = None  # set by quality
    id_faces: list[Face] = field(default_factory=list)  # set by quality
    ocr: OcrResult | None = None  # set by extract
    qr: SecureQrData | None = None  # set by extract
    qr_certificate: str | None = None  # set by extract when the signature verifies
    fields: ExtractedFields = field(default_factory=ExtractedFields)  # set by extract, refined by aadhaar_qr
    id_face_embedding: np.ndarray | None = None  # set by duplicates
    qr_photo_embedding: np.ndarray | None = None  # set by aadhaar_qr
    index_keys: IndexKeys = field(default_factory=IndexKeys)  # set by duplicates
    conflicts: list[str] = field(default_factory=list)  # verification ids to re-flag, set by duplicates
    results: dict[str, CheckResult] = field(default_factory=dict)
