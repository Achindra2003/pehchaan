"""Minimal ES256 JWS and EC JWK helpers (RFC 7515/7517/7518), enough for passes, SD-JWT and OpenID4VP."""

from __future__ import annotations

import base64
import hashlib
import json
from typing import Any

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.utils import decode_dss_signature, encode_dss_signature


class JoseError(ValueError):
    pass


def b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def b64url_decode(text: str) -> bytes:
    try:
        return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))
    except (ValueError, TypeError) as exc:
        raise JoseError("invalid base64url") from exc


def sign(payload: dict[str, Any], key: ec.EllipticCurvePrivateKey, *, typ: str, kid: str | None = None) -> str:
    header = {"alg": "ES256", "typ": typ, **({"kid": kid} if kid else {})}
    signing_input = f"{_encode_json(header)}.{_encode_json(payload)}"
    r, s = decode_dss_signature(key.sign(signing_input.encode(), ec.ECDSA(hashes.SHA256())))
    return f"{signing_input}.{b64url(r.to_bytes(32, 'big') + s.to_bytes(32, 'big'))}"


def verify(token: str, key: ec.EllipticCurvePublicKey) -> tuple[dict[str, Any], dict[str, Any]]:
    header, payload, signing_input, signature = split(token)
    if header.get("alg") != "ES256":
        raise JoseError("unsupported algorithm")
    if len(signature) != 64:
        raise JoseError("bad signature length")
    der = encode_dss_signature(int.from_bytes(signature[:32], "big"), int.from_bytes(signature[32:], "big"))
    try:
        key.verify(der, signing_input.encode(), ec.ECDSA(hashes.SHA256()))
    except InvalidSignature as exc:
        raise JoseError("signature does not verify") from exc
    return header, payload


def split(token: str) -> tuple[dict[str, Any], dict[str, Any], str, bytes]:
    parts = token.split(".")
    if len(parts) != 3:
        raise JoseError("not a compact JWS")
    try:
        header = json.loads(b64url_decode(parts[0]))
        payload = json.loads(b64url_decode(parts[1]))
    except json.JSONDecodeError as exc:
        raise JoseError("invalid JSON in JWS") from exc
    return header, payload, f"{parts[0]}.{parts[1]}", b64url_decode(parts[2])


def public_jwk(key: ec.EllipticCurvePublicKey) -> dict[str, str]:
    numbers = key.public_numbers()
    return {
        "kty": "EC",
        "crv": "P-256",
        "x": b64url(numbers.x.to_bytes(32, "big")),
        "y": b64url(numbers.y.to_bytes(32, "big")),
    }


def jwk_public_key(jwk: dict[str, Any]) -> ec.EllipticCurvePublicKey:
    if jwk.get("kty") != "EC" or jwk.get("crv") != "P-256":
        raise JoseError("only EC P-256 keys are supported")
    x = int.from_bytes(b64url_decode(jwk["x"]), "big")
    y = int.from_bytes(b64url_decode(jwk["y"]), "big")
    return ec.EllipticCurvePublicNumbers(x, y, ec.SECP256R1()).public_key()


def key_id(key: ec.EllipticCurvePublicKey) -> str:
    der = key.public_bytes(serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo)
    return b64url(hashlib.sha256(der).digest()[:12])


def _encode_json(value: dict[str, Any]) -> str:
    return b64url(json.dumps(value, separators=(",", ":"), sort_keys=True).encode())
