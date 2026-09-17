"""UIDAI Secure QR: decode, verify the RSA-2048/SHA-256 signature, and (for tests) encode.

Format (per UIDAI's Secure QR specification, cross-checked with pyaadhaar, MIT):
base-10 big integer -> bytes -> gzip -> fields separated by byte 255 -> JPEG 2000 photo -> [hashes] -> 256-byte signature.
Newer versions start with a "V2"/"V3"/... marker and append the last 4 digits of the mobile number.
The QR data is used in memory only; UIDAI's offline verification rules don't allow storing it.
"""

from __future__ import annotations

import gzip
import logging
import re
import zlib
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from cryptography import x509
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from defusedxml import ElementTree

logger = logging.getLogger(__name__)

FIELDS = [
    "email_mobile_status", "reference_id", "name", "dob", "gender", "care_of", "district", "landmark",
    "house", "location", "pincode", "post_office", "state", "street", "sub_district", "vtc",
]  # fmt: skip
SIGNATURE_BYTES = 256
HASH_BYTES = 32


class SecureQrError(ValueError):
    pass


@dataclass(frozen=True)
class SecureQrData:
    name: str
    dob: date | None
    year_of_birth: int | None
    gender: str | None
    last4: str | None
    reference_id: str | None
    version: str | None
    photo: bytes | None
    signed_data: bytes
    signature: bytes
    legacy_unsigned: bool = False
    legacy_uid: str | None = None


def decode(text: str) -> SecureQrData:
    text = text.strip()
    if text.startswith("<") or "PrintLetterBarcodeData" in text:
        return _decode_legacy_xml(text)
    if not text.isdigit():
        raise SecureQrError("not an Aadhaar QR code")

    number = int(text)
    try:
        data = zlib.decompress(number.to_bytes((number.bit_length() + 7) // 8, "big"), 16 + zlib.MAX_WBITS)
    except zlib.error as exc:
        raise SecureQrError("payload is not compressed Secure QR data") from exc
    if len(data) < SIGNATURE_BYTES + 20:
        raise SecureQrError("payload too short")

    versioned = data[:1] == b"V" and data[1:2].isdigit()
    names = ["version", *FIELDS, "mobile_last4"] if versioned else list(FIELDS)
    values: dict[str, str] = {}
    start = 0
    for name in names:
        end = data.find(b"\xff", start)
        if end < 0:
            raise SecureQrError("missing field delimiter")
        values[name] = data[start:end].decode("latin-1")
        start = end + 1

    photo_end = len(data) - SIGNATURE_BYTES
    if not versioned:
        status = int(values["email_mobile_status"]) if values["email_mobile_status"].isdigit() else 0
        photo_end -= HASH_BYTES * (2 if status == 3 else 1 if status in (1, 2) else 0)

    dob, year = _parse_dob(values["dob"])
    reference_id = values["reference_id"] or None
    return SecureQrData(
        name=values["name"],
        dob=dob,
        year_of_birth=year,
        gender=values["gender"][:1].upper() or None,
        last4=reference_id[:4] if reference_id else None,
        reference_id=reference_id,
        version=values.get("version"),
        photo=data[start:photo_end] or None,
        signed_data=data[: len(data) - SIGNATURE_BYTES],
        signature=data[len(data) - SIGNATURE_BYTES :],
    )


def _parse_dob(value: str) -> tuple[date | None, int | None]:
    value = value.strip()
    if m := re.fullmatch(r"(\d{2})[-/](\d{2})[-/](\d{4})", value):
        try:
            parsed = date(int(m[3]), int(m[2]), int(m[1]))
            return parsed, parsed.year
        except ValueError:
            return None, None
    if re.fullmatch(r"\d{4}", value):
        return None, int(value)
    return None, None


def _decode_legacy_xml(text: str) -> SecureQrData:
    """Pre-2018 Aadhaar QR: plain XML, no signature. Readable, but proves nothing."""
    try:
        root = ElementTree.fromstring(text[text.find("<PrintLetterBarcodeData") :] if "<?xml" in text else text)
    except (ElementTree.ParseError, ValueError) as exc:  # defusedxml raises ValueError subclasses on attacks
        raise SecureQrError("unreadable legacy QR") from exc
    attrs = root.attrib
    dob, year = _parse_dob(attrs.get("dob", "").replace("/", "-"))
    if year is None and attrs.get("yob", "").isdigit():
        year = int(attrs["yob"])
    uid = attrs.get("uid")
    return SecureQrData(
        name=attrs.get("name", ""),
        dob=dob,
        year_of_birth=year,
        gender=(attrs.get("gender") or "")[:1].upper() or None,
        last4=uid[-4:] if uid else None,
        reference_id=None,
        version=None,
        photo=None,
        signed_data=b"",
        signature=b"",
        legacy_unsigned=True,
        legacy_uid=uid,
    )


class CertificateStore:
    """UIDAI signing certificates. Accepts a file or a directory (certificates rotate)."""

    def __init__(self, keys: list[tuple[str, rsa.RSAPublicKey]]) -> None:
        self.keys = keys

    @classmethod
    def load(cls, path: Path) -> CertificateStore:
        files = sorted(path.glob("*")) if path.is_dir() else [path] if path.exists() else []
        keys: list[tuple[str, rsa.RSAPublicKey]] = []
        for file in files:
            if file.suffix.lower() not in {".cer", ".crt", ".pem", ".der"}:
                continue
            if key := _load_key(file.read_bytes()):
                keys.append((file.name, key))
            else:
                logger.warning("could not load certificate %s", file.name)
        return cls(keys)

    @property
    def available(self) -> bool:
        return bool(self.keys)

    def verify(self, qr: SecureQrData) -> str | None:
        """Name of the certificate that validates the signature, or None."""
        if qr.legacy_unsigned:
            return None
        for name, key in self.keys:
            try:
                key.verify(qr.signature, qr.signed_data, padding.PKCS1v15(), hashes.SHA256())
                return name
            except InvalidSignature:
                continue
        return None


def _load_key(raw: bytes) -> rsa.RSAPublicKey | None:
    loaders = (
        lambda: x509.load_der_x509_certificate(raw).public_key(),
        lambda: x509.load_pem_x509_certificate(raw).public_key(),
        lambda: serialization.load_pem_public_key(raw),
    )
    for loader in loaders:
        try:
            key = loader()
        except ValueError:
            continue
        if isinstance(key, rsa.RSAPublicKey):
            return key
    return None


def encode(
    *,
    name: str,
    dob: str,
    gender: str,
    reference_id: str,
    private_key: rsa.RSAPrivateKey,
    photo: bytes = b"",
    version: str = "V2",
) -> str:
    """Build a Secure-QR-format payload signed with `private_key`. For tests and synthetic data only."""
    values = {name_: "" for name_ in FIELDS} | {
        "email_mobile_status": "0",
        "reference_id": reference_id,
        "name": name,
        "dob": dob,
        "gender": gender,
        "state": "Karnataka",
        "district": "Bengaluru",
    }
    parts = [version, *(values[f] for f in FIELDS), "0000"]
    body = b"\xff".join(part.encode("latin-1") for part in parts) + b"\xff" + photo
    signature = private_key.sign(body, padding.PKCS1v15(), hashes.SHA256())
    return str(int.from_bytes(gzip.compress(body + signature, mtime=0), "big"))
