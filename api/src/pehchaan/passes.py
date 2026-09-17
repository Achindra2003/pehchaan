"""Pehchaan Pass: verify once, reuse at every later event on the same platform.

A pass is an ES256-signed token Pehchaan returns to Hackingly after a verified registration. It is bound to the
Hackingly account (keyed hash of the account id), carries only what future eligibility checks need (name, DOB,
evidence level, student validity), expires (12 months, or when the college ID does), and can be revoked,
automatically when fraud is later found on the verification it came from. Re-verification then costs no OCR,
no images and a few milliseconds.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta

from pehchaan import jose
from pehchaan.domain.models import DocType, EvidenceLevel, ExtractedFields, FieldSource, VerificationResult
from pehchaan.security import Crypto

PASS_TYPE = "pehchaan-pass+jwt"  # noqa: S105 - a JWT type, not a secret


class PassError(ValueError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


@dataclass(frozen=True)
class PassClaims:
    pass_id: str
    tenant: str
    subject: str
    level: EvidenceLevel
    doc_type: DocType
    name: str
    dob: date | None
    year_of_birth: int | None
    dob_confirmed: bool
    student_until: date | None
    verification_id: str
    issued_at: datetime
    expires_at: datetime


class PassAuthority:
    def __init__(self, crypto: Crypto, validity_days: int) -> None:
        self._crypto = crypto
        self._key = crypto.signing_key
        self._kid = jose.key_id(crypto.signing_key.public_key())
        self._validity = timedelta(days=validity_days)

    def subject_hash(self, tenant: str, subject_id: str) -> str:
        return self._crypto.id_hash(f"subject:{tenant}:{subject_id}")

    def issue(
        self, result: VerificationResult, fields: ExtractedFields, form_name: str, tenant: str, subject_id: str
    ) -> tuple[str, PassClaims]:
        now = datetime.now(UTC)
        expires = now + self._validity
        student_until = fields.valid_until if fields.doc_type is DocType.COLLEGE_ID else None
        if student_until:
            expires = min(expires, datetime.combine(student_until, datetime.max.time(), UTC))
        claims = PassClaims(
            pass_id=f"pass_{uuid.uuid4().hex}",
            tenant=tenant,
            subject=self.subject_hash(tenant, subject_id),
            level=result.evidence_level,
            doc_type=fields.doc_type,
            name=form_name,
            dob=fields.dob,
            year_of_birth=fields.year_of_birth,
            dob_confirmed=fields.dob_source in {FieldSource.QR_SIGNED, FieldSource.AADHAAR_VC},
            student_until=student_until,
            verification_id=result.verification_id,
            issued_at=now,
            expires_at=expires,
        )
        payload = {
            "iss": "pehchaan",
            "jti": claims.pass_id,
            "ten": tenant,
            "sub": claims.subject,
            "lvl": int(claims.level),
            "doc": claims.doc_type.value,
            "name": claims.name,
            "dob": claims.dob.isoformat() if claims.dob else None,
            "yob": claims.year_of_birth,
            "dobc": claims.dob_confirmed,
            "stu": student_until.isoformat() if student_until else None,
            "vid": claims.verification_id,
            "iat": int(now.timestamp()),
            "exp": int(expires.timestamp()),
        }
        return jose.sign(payload, self._key, typ=PASS_TYPE, kid=self._kid), claims

    def verify(self, token: str, tenant: str, subject_id: str) -> PassClaims:
        try:
            header, payload = jose.verify(token, self._key.public_key())
        except jose.JoseError as exc:
            raise PassError("PASS_INVALID") from exc
        if header.get("typ") != PASS_TYPE or payload.get("iss") != "pehchaan":
            raise PassError("PASS_INVALID")
        if payload.get("ten") != tenant or payload.get("sub") != self.subject_hash(tenant, subject_id):
            raise PassError("PASS_SUBJECT_MISMATCH")
        if datetime.now(UTC).timestamp() > payload["exp"]:
            raise PassError("PASS_EXPIRED")
        return PassClaims(
            pass_id=payload["jti"],
            tenant=payload["ten"],
            subject=payload["sub"],
            level=EvidenceLevel(payload["lvl"]),
            doc_type=DocType(payload["doc"]),
            name=payload["name"],
            dob=date.fromisoformat(payload["dob"]) if payload.get("dob") else None,
            year_of_birth=payload.get("yob"),
            dob_confirmed=bool(payload.get("dobc")),
            student_until=date.fromisoformat(payload["stu"]) if payload.get("stu") else None,
            verification_id=payload["vid"],
            issued_at=datetime.fromtimestamp(payload["iat"], UTC),
            expires_at=datetime.fromtimestamp(payload["exp"], UTC),
        )
