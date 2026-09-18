"""Synthetic SPECIMEN documents for tests and evaluation.

Every card carries a visible SPECIMEN watermark and a "not a valid document" footer, uses fictional people
and numbers, and has no emblems or official artwork. Secure QR codes are signed with a locally generated
TEST key, never a UIDAI key, so they only verify when Pehchaan is pointed at the test certificate.
"""

from __future__ import annotations

import io
import random
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import numpy as np
import qrcode
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID
from PIL import Image, ImageDraw, ImageFilter, ImageFont
from stdnum import verhoeff

from pehchaan.aadhaar import secure_qr

CARD_SIZE = (1000, 630)
INK = (25, 25, 30)


@dataclass(frozen=True)
class Person:
    name: str
    father: str
    dob: date
    gender: str  # "F" or "M"
    aadhaar: str
    reference_time: str

    @property
    def gender_word(self) -> str:
        return "FEMALE" if self.gender == "F" else "MALE"


FIRST = {"F": ["Asha", "Priya", "Kavya", "Meera", "Ananya", "Divya", "Lakshmi", "Sneha"], "M": ["Arjun", "Rahul", "Karthik", "Vikram", "Rohan", "Aditya", "Nikhil", "Siddharth"]}  # fmt: skip
LAST = ["Rao", "Sharma", "Iyer", "Reddy", "Nair", "Gupta", "Menon", "Patil", "Hegde", "Kulkarni"]


def make_person(rng: random.Random, *, dob: date | None = None, gender: str | None = None) -> Person:
    gender = gender or rng.choice("FM")
    last = rng.choice(LAST)
    body = str(rng.randint(2, 9)) + "".join(str(rng.randint(0, 9)) for _ in range(10))
    return Person(
        name=f"{rng.choice(FIRST[gender])} {last}",
        father=f"{rng.choice(FIRST['M'])} {last}",
        dob=dob or date(rng.randint(1996, 2007), rng.randint(1, 12), rng.randint(1, 28)),
        gender=gender,
        aadhaar=body + verhoeff.calc_check_digit(body),
        reference_time=f"2025{rng.randint(1, 12):02d}{rng.randint(1, 28):02d}{rng.randint(0, 23):02d}0000000",
    )


def pan_for(person: Person, rng: random.Random) -> str:
    letters = "".join(rng.choice("ABCDEFGHJKLMNPQRSTUVWXYZ") for _ in range(3))
    return f"{letters}P{person.name.split()[-1][0]}{rng.randint(1000, 9999)}{rng.choice('ABCDEFGHJKLMNPQRSTUVWXYZ')}"


# --- test signing key ---------------------------------------------------------------------


def make_test_signing_key(directory: Path) -> rsa.RSAPrivateKey:
    """Create (once) a TEST key and self-signed certificate standing in for UIDAI's in tests."""
    directory.mkdir(parents=True, exist_ok=True)
    key_path, cert_path = directory / "test-signing-key.key", directory / "test-uidai-NOT-REAL.pem"
    if key_path.exists() and cert_path.exists():
        return serialization.load_pem_private_key(key_path.read_bytes(), password=None)  # type: ignore[return-value]
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    subject = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "Pehchaan TEST signer - not UIDAI")])
    now = datetime.now(UTC)
    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(subject)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(days=1))
        .not_valid_after(now + timedelta(days=365))
        .sign(key, hashes.SHA256())
    )
    key_path.write_bytes(
        key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption())
    )
    cert_path.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    return key


def secure_qr_for(person: Person, key: rsa.RSAPrivateKey) -> str:
    return secure_qr.encode(
        name=person.name,
        dob=person.dob.strftime("%d-%m-%Y"),
        gender=person.gender,
        reference_id=person.aadhaar[-4:] + person.reference_time,
        private_key=key,
    )


# --- rendering -----------------------------------------------------------------------------------


def _font(size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.load_default(size=size)


def _base(title: str, fill: tuple[int, int, int]) -> tuple[Image.Image, ImageDraw.ImageDraw]:
    card = Image.new("RGB", CARD_SIZE, fill)
    draw = ImageDraw.Draw(card)
    draw.rectangle((0, 0, CARD_SIZE[0], 90), fill=tuple(max(0, c - 40) for c in fill))
    draw.text((40, 26), title, font=_font(38), fill=INK)
    return card, draw


def _finish(card: Image.Image) -> Image.Image:
    draw = ImageDraw.Draw(card)
    draw.text((40, 596), "SPECIMEN FOR SOFTWARE TESTING - NOT A VALID DOCUMENT", font=_font(18), fill=(150, 40, 40))
    overlay = Image.new("RGBA", (520, 120), (0, 0, 0, 0))
    ImageDraw.Draw(overlay).text((10, 10), "SPECIMEN", font=_font(96), fill=(200, 40, 40, 45))
    card.paste(overlay.rotate(18, expand=True), (430, 380), overlay.rotate(18, expand=True))
    return card


def _portrait(draw: ImageDraw.ImageDraw, box: tuple[int, int, int, int]) -> None:
    x0, y0, x1, y1 = box
    draw.rectangle(box, fill=(210, 214, 220), outline=(150, 150, 160), width=2)
    cx = (x0 + x1) // 2
    draw.ellipse((cx - 45, y0 + 35, cx + 45, y0 + 135), fill=(170, 175, 185))
    draw.rectangle((cx - 70, y0 + 150, cx + 70, y1 - 5), fill=(170, 175, 185))


def render_aadhaar(
    person: Person,
    *,
    qr_payload: str | None,
    printed_dob: date | None = None,
    masked: bool = False,
    year_only: bool = False,
) -> Image.Image:
    card, draw = _base("GOVERNMENT OF INDIA", (246, 244, 236))
    _portrait(draw, (40, 130, 250, 390))
    dob = printed_dob or person.dob
    draw.text((290, 150), person.name, font=_font(40), fill=INK)
    dob_text = f"Year of Birth: {dob.year}" if year_only else f"DOB: {dob.strftime('%d/%m/%Y')}"
    draw.text((290, 215), dob_text, font=_font(36), fill=INK)
    draw.text((290, 275), person.gender_word, font=_font(36), fill=INK)
    number = (
        f"XXXX XXXX {person.aadhaar[-4:]}"
        if masked
        else f"{person.aadhaar[:4]} {person.aadhaar[4:8]} {person.aadhaar[8:]}"
    )
    draw.text((290, 470), number, font=_font(58), fill=INK)
    if qr_payload:
        card.paste(_qr_image(qr_payload, 330), (650, 110))
    return _finish(card)


def render_pan(person: Person, pan: str) -> Image.Image:
    card, draw = _base("INCOME TAX DEPARTMENT", (228, 236, 246))
    draw.text((620, 30), "GOVT. OF INDIA", font=_font(30), fill=INK)
    draw.text((40, 110), "Permanent Account Number Card", font=_font(30), fill=INK)
    draw.text((40, 155), pan, font=_font(48), fill=INK)
    draw.text((40, 230), "Name", font=_font(26), fill=(80, 80, 90))
    draw.text((40, 262), person.name.upper(), font=_font(40), fill=INK)
    draw.text((40, 330), "Father's Name", font=_font(26), fill=(80, 80, 90))
    draw.text((40, 362), person.father.upper(), font=_font(40), fill=INK)
    draw.text((40, 430), "Date of Birth", font=_font(26), fill=(80, 80, 90))
    draw.text((40, 462), person.dob.strftime("%d/%m/%Y"), font=_font(40), fill=INK)
    _portrait(draw, (760, 150, 950, 390))
    return _finish(card)


def render_college_id(person: Person, *, institution: str, roll: str, valid_until: date) -> Image.Image:
    card, draw = _base(institution, (240, 246, 240))
    draw.text((40, 110), "STUDENT IDENTITY CARD", font=_font(34), fill=(30, 90, 50))
    _portrait(draw, (40, 170, 240, 420))
    draw.text((280, 180), f"Name: {person.name}", font=_font(38), fill=INK)
    draw.text((280, 245), f"Roll No: {roll}", font=_font(34), fill=INK)
    draw.text((280, 305), "Course: B.E. Computer Science", font=_font(34), fill=INK)
    draw.text((280, 365), f"Date of Birth: {person.dob.strftime('%d/%m/%Y')}", font=_font(34), fill=INK)
    draw.text((280, 425), f"Valid upto: {valid_until.strftime('%m/%Y')}", font=_font(34), fill=INK)
    return _finish(card)


def _qr_image(payload: str, size: int) -> Image.Image:
    qr = qrcode.QRCode(error_correction=qrcode.constants.ERROR_CORRECT_M, box_size=4, border=2)
    qr.add_data(payload)
    qr.make(fit=True)
    return qr.make_image().convert("RGB").resize((size, size), Image.NEAREST)


# --- attacks and capture ----------------------------------------------------------------------------


def paste_edit(card: Image.Image, box: tuple[int, int, int, int], text: str, size: int) -> Image.Image:
    """Simulate a crude digital edit: recompress the card, then paint fresh text over one field."""
    buffer = io.BytesIO()
    card.save(buffer, "JPEG", quality=70)
    edited = Image.open(io.BytesIO(buffer.getvalue())).convert("RGB")
    draw = ImageDraw.Draw(edited)
    draw.rectangle(box, fill=(246, 244, 236))
    draw.text((box[0], box[1] + 4), text, font=_font(size), fill=(10, 10, 10))
    return edited


def photograph(card: Image.Image, rng: random.Random, *, blur: float = 0.0, quality: int = 88) -> bytes:
    """Simulate a phone photo: desk background, slight rotation, lighting, sensor noise, JPEG."""
    desk = tuple(rng.randint(60, 140) for _ in range(3))
    canvas = Image.new("RGB", (1300, 950), desk)
    rotated = card.rotate(rng.uniform(-2.5, 2.5), resample=Image.BICUBIC, expand=True, fillcolor=desk)
    canvas.paste(
        rotated,
        ((1300 - rotated.width) // 2 + rng.randint(-30, 30), (950 - rotated.height) // 2 + rng.randint(-20, 20)),
    )
    pixels = np.asarray(canvas).astype(np.float32) * rng.uniform(0.9, 1.05)
    pixels += np.random.default_rng(rng.randint(0, 2**32 - 1)).normal(0, 3.0, pixels.shape)
    photo = Image.fromarray(np.clip(pixels, 0, 255).astype(np.uint8))
    if blur:
        photo = photo.filter(ImageFilter.GaussianBlur(blur))
    buffer = io.BytesIO()
    photo.save(buffer, "JPEG", quality=quality)
    return buffer.getvalue()


# --- Aadhaar App test wallet ------------------------------------------------------------------------


def make_test_uidai_issuer(directory: Path):
    """A TEST stand-in for UIDAI's SD-JWT issuer key, written as a JWKS file Pehchaan can be pointed at."""
    import json as _json

    from cryptography.hazmat.primitives.asymmetric import ec

    from pehchaan import jose

    directory.mkdir(parents=True, exist_ok=True)
    key_path, jwks_path = directory / "test-uidai-issuer.key", directory / "uidai-jwks.json"
    if key_path.exists() and jwks_path.exists():
        key = serialization.load_pem_private_key(key_path.read_bytes(), password=None)
    else:
        key = ec.generate_private_key(ec.SECP256R1())
        key_path.write_bytes(
            key.private_bytes(
                serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()
            )
        )
        jwk = {**jose.public_jwk(key.public_key()), "kid": jose.key_id(key.public_key()), "use": "sig", "alg": "ES256"}
        jwks_path.write_text(_json.dumps({"keys": [jwk]}))
    return key


def issue_test_aadhaar_credential(issuer_key, holder_key, claims: dict) -> str:
    """Issue an SD-JWT shaped like the Aadhaar App credential, every claim selectively disclosable."""
    import hashlib
    import json as _json
    import secrets as _secrets
    import time as _time

    from pehchaan import jose

    disclosures = [
        jose.b64url(_json.dumps([_secrets.token_urlsafe(16), name, value], separators=(",", ":")).encode())
        for name, value in claims.items()
    ]
    payload = {
        "iss": "https://uidai.gov.in",
        "iat": int(_time.time()),
        "exp": int(_time.time()) + 3600,
        "vct": "AadhaarCredential",
        "_sd_alg": "sha-256",
        "_sd": sorted(jose.b64url(hashlib.sha256(d.encode()).digest()) for d in disclosures),
        "cnf": {"jwk": jose.public_jwk(holder_key.public_key())},
    }
    token = jose.sign(payload, issuer_key, typ="vc+sd-jwt", kid=jose.key_id(issuer_key.public_key()))
    return token + "~" + "".join(f"{d}~" for d in disclosures)


def present_test_credential(issued: str, disclose: set[str], holder_key, *, audience: str, nonce: str) -> str:
    """What the Aadhaar App would post back: only the chosen disclosures, bound to this request."""
    import hashlib
    import json as _json
    import time as _time

    from pehchaan import jose

    parts = issued.split("~")
    chosen = [d for d in parts[1:] if d and _json.loads(jose.b64url_decode(d))[1] in disclose]
    presented = parts[0] + "~" + "".join(f"{d}~" for d in chosen)
    kb = {
        "aud": audience,
        "nonce": nonce,
        "iat": int(_time.time()),
        "sd_hash": jose.b64url(hashlib.sha256(presented.encode()).digest()),
    }
    return presented + jose.sign(kb, holder_key, typ="kb+jwt")


def screen_photo(card: Image.Image, rng: random.Random) -> bytes:
    """Simulate photographing the card on a screen: subpixel grid, then resampling at a different pitch.

    That mismatch is what produces moire in real life, which is what the recapture check looks for.
    """
    width = 1400
    shown = card.resize((width, round(card.height * width / card.width)), Image.LANCZOS)
    pixels = np.asarray(shown).astype(np.float32)
    # RGB subpixel stripes plus the dark gaps between pixels
    stripes = np.zeros((1, pixels.shape[1], 3), dtype=np.float32)
    for channel in range(3):
        stripes[0, channel::3, channel] = 1.0
    pixels *= 0.55 + 0.75 * stripes
    pixels[:, ::3] *= 0.9
    pixels[::3, :] *= 0.92
    glow = np.linspace(1.12, 0.94, pixels.shape[1], dtype=np.float32)[None, :, None]
    screen = Image.fromarray(np.clip(pixels * glow, 0, 255).astype(np.uint8))
    # The camera samples that grid at its own pitch: the beat between the two is the moire
    captured = screen.resize((round(width * 0.62), round(screen.height * 0.62)), Image.BILINEAR)
    return photograph(captured, rng, quality=90)
