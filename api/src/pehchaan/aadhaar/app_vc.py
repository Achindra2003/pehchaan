"""Aadhaar App verifiable credentials over OpenID4VP (cross-device flow), verifier side.

Per UIDAI's Aadhaar App documentation (docs.uidai.gov.in): the verifier shows a QR with a signed request, the
resident scans it with the Aadhaar App, authenticates with their face, chooses what to share, and the app posts
an SD-JWT presentation (issuer https://uidai.gov.in, ES256, keys from UIDAI's JWKS, holder binding via `cnf`).

Pehchaan asks for the least data the event needs: an 18+ event gets `ResidentName` + `AgeAbove18`, never a DOB
or a photo. Production use requires OVSE onboarding with UIDAI; until then the flow runs against a test issuer.
"""

from __future__ import annotations

import base64
import hashlib
import json
import logging
import time
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any

from cryptography.hazmat.primitives.asymmetric import ec

from pehchaan import jose
from pehchaan.domain.policy import EventPolicy

logger = logging.getLogger(__name__)

UIDAI_ISSUER = "https://uidai.gov.in"
REQUEST_TTL_SECONDS = 600
KB_MAX_AGE_SECONDS = 300
AGE_CLAIMS = {18: "AgeAbove18", 50: "AgeAbove50", 60: "AgeAbove60", 75: "AgeAbove75"}


class PresentationError(ValueError):
    pass


@dataclass(frozen=True)
class AadhaarAppClaims:
    name: str | None
    dob: date | None
    age_above: dict[int, bool]
    gender: str | None
    masked_uid: str | None
    photo: bytes | None
    issuer: str
    key_bound: bool


class IssuerKeys:
    def __init__(self, keys: dict[str, ec.EllipticCurvePublicKey]) -> None:
        self.keys = keys

    @classmethod
    def load(cls, path: Path) -> IssuerKeys:
        if not path.exists():
            return cls({})
        document = json.loads(path.read_text())
        keys = {}
        for jwk in document.get("keys", []):
            try:
                keys[jwk.get("kid") or jose.key_id(jose.jwk_public_key(jwk))] = jose.jwk_public_key(jwk)
            except (jose.JoseError, KeyError):
                logger.warning("skipping unsupported JWKS entry")
        return cls(keys)

    @property
    def available(self) -> bool:
        return bool(self.keys)


def requested_claims(policy: EventPolicy) -> list[str]:
    """Data minimisation: only what this event's rules need."""
    claims = ["ResidentName"]
    if policy.min_age in AGE_CLAIMS and policy.max_age is None:
        claims.append(AGE_CLAIMS[policy.min_age])
    elif policy.min_age is not None or policy.max_age is not None:
        claims.append("Dob")
    if policy.guardian_consent_under == 18 and "AgeAbove18" not in claims and "Dob" not in claims:
        claims.append("AgeAbove18")
    return claims


def presentation_definition(session_id: str, claims: list[str]) -> dict[str, Any]:
    return {
        "id": session_id,
        "input_descriptors": [
            {
                "id": "aadhaar",
                "purpose": "Verify identity and eligibility for event registration",
                "constraints": {
                    "limit_disclosure": "required",
                    "fields": [{"path": [f"$.credentialSubject.{claim}", f"$.{claim}"]} for claim in claims],
                },
            }
        ],
    }


def request_object(
    *,
    session_id: str,
    nonce: str,
    client_id: str,
    response_uri: str,
    claims: list[str],
    key: ec.EllipticCurvePrivateKey,
) -> str:
    now = int(time.time())
    payload = {
        "iss": client_id,
        "client_id": client_id,
        "response_type": "vp_token",
        "response_mode": "direct_post",
        "response_uri": response_uri,
        "scope": "openid vp_token",
        "nonce": nonce,
        "state": session_id,
        "presentation_definition": presentation_definition(session_id, claims),
        "iat": now,
        "exp": now + REQUEST_TTL_SECONDS,
    }
    return jose.sign(payload, key, typ="oauth-authz-req+jwt", kid=jose.key_id(key.public_key()))


def verify_presentation(token: str, issuers: IssuerKeys, *, audience: str, nonce: str) -> AadhaarAppClaims:
    if "~" not in token:
        raise PresentationError("not an SD-JWT presentation")
    parts = token.split("~")
    issuer_jwt, disclosures, kb_jwt = parts[0], [d for d in parts[1:-1] if d], parts[-1]

    try:
        header, payload, _, _ = jose.split(issuer_jwt)
        key = issuers.keys.get(header.get("kid", ""))
        if key is None:
            raise PresentationError("issuer key not trusted")
        jose.verify(issuer_jwt, key)
    except jose.JoseError as exc:
        raise PresentationError("issuer signature invalid") from exc
    if payload.get("iss") != UIDAI_ISSUER:
        raise PresentationError("unexpected issuer")
    if "exp" in payload and time.time() > payload["exp"]:
        raise PresentationError("credential expired")

    digests = set(_collect_sd_digests(payload))
    disclosed: dict[str, Any] = dict(payload.get("credentialSubject", {}) or {})
    for disclosure in disclosures:
        digest = jose.b64url(hashlib.sha256(disclosure.encode()).digest())
        if digest not in digests:
            raise PresentationError("disclosure not issued in this credential")
        try:
            decoded = json.loads(jose.b64url_decode(disclosure))
        except (json.JSONDecodeError, jose.JoseError) as exc:
            raise PresentationError("malformed disclosure") from exc
        if not isinstance(decoded, list) or len(decoded) != 3:
            raise PresentationError("malformed disclosure")
        disclosed[decoded[1]] = decoded[2]

    key_bound = False
    holder = (payload.get("cnf") or {}).get("jwk")
    if holder:
        if not kb_jwt:
            raise PresentationError("key binding required")
        try:
            kb_header, kb = jose.verify(kb_jwt, jose.jwk_public_key(holder))
        except jose.JoseError as exc:
            raise PresentationError("key binding signature invalid") from exc
        presented = token[: len(token) - len(kb_jwt)]
        if kb_header.get("typ") != "kb+jwt" or kb.get("aud") != audience or kb.get("nonce") != nonce:
            raise PresentationError("key binding does not match this request")
        if abs(time.time() - kb.get("iat", 0)) > KB_MAX_AGE_SECONDS:
            raise PresentationError("key binding too old")
        if kb.get("sd_hash") != jose.b64url(hashlib.sha256(presented.encode()).digest()):
            raise PresentationError("key binding covers different disclosures")
        key_bound = True

    return AadhaarAppClaims(
        name=disclosed.get("ResidentName"),
        dob=_parse_date(disclosed.get("Dob")),
        age_above={age: _truthy(disclosed[claim]) for age, claim in AGE_CLAIMS.items() if claim in disclosed},
        gender=(str(disclosed["Gender"])[:1].upper() if disclosed.get("Gender") else None),
        masked_uid=disclosed.get("MaskedUID"),
        photo=base64.b64decode(disclosed["ResidentImage"]) if disclosed.get("ResidentImage") else None,
        issuer=payload["iss"],
        key_bound=key_bound,
    )


def _collect_sd_digests(value: Any) -> list[str]:
    if isinstance(value, dict):
        found = [d for d in value.get("_sd", []) if isinstance(d, str)]
        for child in value.values():
            found += _collect_sd_digests(child)
        return found
    if isinstance(value, list):
        return [d for item in value for d in _collect_sd_digests(item)]
    return []


def _truthy(value: Any) -> bool:
    return value is True or str(value).strip().lower() in {"true", "y", "yes", "1"}


def _parse_date(value: Any) -> date | None:
    if not value:
        return None
    text = str(value)
    for fmt in ("%d-%m-%Y", "%Y-%m-%d", "%d/%m/%Y"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    return None
