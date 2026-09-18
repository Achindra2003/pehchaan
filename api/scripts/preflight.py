"""Check everything Pehchaan needs before a demo, and say what each missing piece would unlock.

    uv run python scripts/preflight.py

Nothing here is required to run: the demo works with zero configuration. Each line tells you what you get
by adding the optional piece, and the exact command or file that adds it.
"""

from __future__ import annotations

import importlib
import os
import socket
import sys
from pathlib import Path

from pehchaan.config import Settings

API = Path(__file__).resolve().parents[1]
OK, WARN, GAP = "ready  ", "option ", "missing"


def main() -> int:
    settings = Settings(_env_file=API / ".env")  # type: ignore[call-arg]
    rows: list[tuple[str, str, str]] = []

    rows.append(_packages())
    rows.append(_models(settings))
    rows.append(_wechat(settings))
    rows.append(_certificates(settings))
    rows.append(_jwks(settings))
    rows.append(_demo_cards())
    rows.append(_web_build())
    rows.append(_textract(settings))
    rows.append(_copilot(settings))
    rows.append(_keys(settings))
    rows.append(_port())

    width = max(len(name) for _, name, _ in rows)
    print()
    for state, name, detail in rows:
        print(f"  [{state}] {name.ljust(width)}  {detail}")
    blocked = [name for state, name, _ in rows if state == GAP]
    print()
    if blocked:
        print(f"  {len(blocked)} missing: {', '.join(blocked)}")
    print("  demo: uv run python scripts/demo.py   ->  http://localhost:8000\n")
    return 1 if blocked else 0


def _packages() -> tuple[str, str, str]:
    missing = []
    for module, why in [
        ("cv2", "images, faces, QR"),
        ("rapidocr_onnxruntime", "local OCR"),
        ("onnxruntime", "liveness"),
        ("pdqhash", "duplicate images"),
        ("indic_namematch", "name matching"),
        ("cryptography", "signatures"),
    ]:
        try:
            importlib.import_module(module)
        except ImportError:
            missing.append(f"{module} ({why})")
    if missing:
        return GAP, "python packages", f"run `uv sync`; missing {', '.join(missing)}"
    import cv2

    contrib = hasattr(cv2, "wechat_qrcode_WeChatQRCode")
    return (OK, "python packages", f"OpenCV {cv2.__version__}{'' if contrib else ' WITHOUT contrib: run `uv sync`'}")


def _models(settings: Settings) -> tuple[str, str, str]:
    needed = ["face_detection_yunet_2023mar.onnx", "face_recognition_sface_2021dec.onnx", "minifasnet_v2.onnx"]
    missing = [name for name in needed if not (API / settings.models_dir / name).exists()]
    if missing:
        return GAP, "face models", "no face match or liveness: run `uv run python scripts/download_models.py`"
    return OK, "face models", "face match on the ID, selfie match, passive liveness"


def _wechat(settings: Settings) -> tuple[str, str, str]:
    directory = API / settings.models_dir / "wechat"
    if not (directory / "detect.caffemodel").exists():
        return GAP, "QR models", "Aadhaar QR often unreadable: run `uv run python scripts/download_models.py`"
    return OK, "QR models", "reads dense Secure QR codes from phone photos"


def _certificates(settings: Settings) -> tuple[str, str, str]:
    path = API / settings.uidai_cert_path
    files = sorted(p.name for p in path.glob("*")) if path.is_dir() else ([path.name] if path.exists() else [])
    certs = [f for f in files if f.lower().endswith((".cer", ".crt", ".pem", ".der"))]
    if not certs:
        return GAP, "UIDAI certificate", f"no signature check, so L3 is unreachable: put the real .cer in {path}"
    if any("NOT-REAL" in name for name in certs):
        return WARN, "UIDAI certificate", f"TEST certificate ({certs[0]}): verifies the demo cards, not real Aadhaars"
    return OK, "UIDAI certificate", f"real Aadhaar signatures verified ({', '.join(certs)})"


def _jwks(settings: Settings) -> tuple[str, str, str]:
    if not (API / settings.uidai_jwks_path).exists():
        return WARN, "Aadhaar App keys", "Aadhaar App path needs UIDAI's JWKS (and OVSE onboarding)"
    return OK, "Aadhaar App keys", "OpenID4VP credentials verified"


def _demo_cards() -> tuple[str, str, str]:
    if not (API / "demo-samples" / "samples.json").exists():
        return WARN, "demo cards", "one-click demo cases: run `uv run python scripts/make_demo_samples.py`"
    return OK, "demo cards", "one-click demo cases on the participant screen"


def _web_build() -> tuple[str, str, str]:
    if not (API.parent / "web" / "dist" / "index.html").exists():
        return GAP, "web build", "API only, no screens: run `npm install && npm run build` in web/"
    return OK, "web build", "participant and organiser screens served by the API"


def _textract(settings: Settings) -> tuple[str, str, str]:
    has_keys = bool(os.environ.get("AWS_ACCESS_KEY_ID") or (Path.home() / ".aws" / "credentials").exists())
    if settings.textract_enabled and has_keys:
        return OK, "AWS Textract", f"live Textract in {settings.aws_region}"
    if has_keys:
        return WARN, "AWS Textract", "credentials found; set PEHCHAAN_TEXTRACT_ENABLED=true to call Textract"
    return WARN, "AWS Textract", "local OCR is used; Hackingly's own textract_response is still accepted"


def _copilot(settings: Settings) -> tuple[str, str, str]:
    if settings.llm_provider == "groq" and settings.groq_api_key.get_secret_value():
        return OK, "reviewer copilot", f"LLM summaries via {settings.groq_model}"
    return WARN, "reviewer copilot", "rules-based summaries; set PEHCHAAN_LLM_PROVIDER=groq + GROQ_API_KEY for LLM"


def _keys(settings: Settings) -> tuple[str, str, str]:
    keys = [k for k in settings.api_keys.get_secret_value().split(",") if k.strip()]
    if keys:
        return OK, "API keys", f"{len(keys)} configured in .env"
    return WARN, "API keys", "scripts/demo.py sets its own key; set PEHCHAAN_API_KEYS for your own runs"


def _port(port: int = 8000) -> tuple[str, str, str]:
    with socket.socket() as probe:
        free = probe.connect_ex(("127.0.0.1", port)) != 0
    return (OK, "port 8000", "free") if free else (WARN, "port 8000", "in use: stop it, or use --port")


if __name__ == "__main__":
    sys.exit(main())
