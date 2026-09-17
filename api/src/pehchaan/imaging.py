"""Decoding uploads into BGR arrays, including password-protected e-Aadhaar PDFs."""

from __future__ import annotations

import io
import re
from datetime import date

import cv2
import numpy as np
from PIL import Image, ImageOps

MAX_SIDE = 2600


class ImageDecodeError(ValueError):
    pass


def decode_image(data: bytes) -> np.ndarray:
    try:
        with Image.open(io.BytesIO(data)) as im:
            rgb = np.asarray(ImageOps.exif_transpose(im).convert("RGB"))
    except Exception as exc:
        raise ImageDecodeError("unreadable image") from exc
    return limit_size(cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR))


def render_pdf(data: bytes, passwords: list[str]) -> np.ndarray:
    import pypdfium2 as pdfium

    for password in [None, *passwords]:
        try:
            pdf = pdfium.PdfDocument(data, password=password)
        except pdfium.PdfiumError:
            continue
        try:
            page = pdf[0]
            rgb = np.asarray(page.render(scale=200 / 72).to_pil().convert("RGB"))
            return limit_size(cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR))
        finally:
            pdf.close()
    raise ImageDecodeError("PDF could not be opened")


def eaadhaar_passwords(name: str | None, dob: date | None) -> list[str]:
    """UIDAI e-Aadhaar PDF password: first four letters of the name in capitals + year of birth."""
    if not name or not dob:
        return []
    letters = re.sub(r"[^A-Za-z]", "", name).upper()
    return [f"{letters[:4]}{dob.year}"]


def limit_size(image: np.ndarray, max_side: int = MAX_SIDE) -> np.ndarray:
    h, w = image.shape[:2]
    scale = max_side / max(h, w)
    if scale >= 1:
        return image
    return cv2.resize(image, (round(w * scale), round(h * scale)), interpolation=cv2.INTER_AREA)


def resize_width(image: np.ndarray, width: int) -> np.ndarray:
    h, w = image.shape[:2]
    if w == width:
        return image
    return cv2.resize(image, (width, round(h * width / w)), interpolation=cv2.INTER_AREA)


def to_jpeg(image: np.ndarray, quality: int = 90) -> bytes:
    ok, buffer = cv2.imencode(".jpg", image, [cv2.IMWRITE_JPEG_QUALITY, quality])
    if not ok:
        raise ImageDecodeError("could not encode image")
    return buffer.tobytes()


def crop_box(image: np.ndarray, box: tuple[float, float, float, float], pad: float = 0.0) -> np.ndarray:
    """Crop a normalised (left, top, right, bottom) box, optionally padded by a fraction of its size."""
    h, w = image.shape[:2]
    left, top, right, bottom = box
    pw, ph = (right - left) * pad, (bottom - top) * pad
    x0, y0 = max(0, int((left - pw) * w)), max(0, int((top - ph) * h))
    x1, y1 = min(w, int((right + pw) * w)), min(h, int((bottom + ph) * h))
    return image[y0:y1, x0:x1]
