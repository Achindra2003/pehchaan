"""One command for the demo: fresh data, demo cards, API and UI on http://localhost:8000.

    uv run python scripts/demo.py            # build the web app first: cd web && npm run build
    uv run python scripts/demo.py --keep     # keep earlier registrations (duplicates will fire)

Credentials: edit api/.env (copy of .env.example) and drop a real UIDAI certificate into api/certs/.
Both are picked up automatically — just restart this script after editing either. Nothing here is
required: with no .env and no certificate, the demo cards still work end to end on their own test key.
"""

from __future__ import annotations

import argparse
import os
import shutil
import sys
from pathlib import Path

API = Path(__file__).resolve().parents[1]
SAMPLES = API / "demo-samples"
DATA = API / "demo-data"
WEB = API.parent / "web" / "dist"
REAL_CERTS = API / "certs"
KEY = "demo-key"
CERT_SUFFIXES = {".cer", ".crt", ".pem", ".der"}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--keep", action="store_true", help="keep earlier registrations")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()

    # Load api/.env (Groq key, AWS keys, etc.) so editing that one file is enough — no exporting needed.
    env_file = API / ".env"
    if env_file.exists():
        from dotenv import load_dotenv

        load_dotenv(env_file, override=True)
        print(f"loaded credentials from {env_file}")
    else:
        print(f"no {env_file} yet: copy .env.example there to add a Groq/AWS key later")

    if not (SAMPLES / "samples.json").exists():
        print("making the demo cards…")
        os.system(f'"{sys.executable}" "{API / "scripts" / "make_demo_samples.py"}"')  # noqa: S605 - fixed path
    if not args.keep:
        shutil.rmtree(DATA, ignore_errors=True)
        print("fresh demo data (duplicate history cleared)")
    if not WEB.is_dir():
        print(f"! no web build at {WEB}: run `npm run build` in web/ to serve the UI from this port")

    # A real certificate dropped into api/certs/ is used automatically. Otherwise fall back to the test
    # certificate that signs the demo cards — even if .env sets PEHCHAAN_UIDAI_CERT_PATH=certs (the
    # .env.example default): an empty or missing cert folder there is treated as "not configured yet",
    # not as "use no certificate at all".
    def has_cert(directory: Path) -> bool:
        return directory.is_dir() and any(p.suffix.lower() in CERT_SUFFIXES for p in directory.glob("*"))

    env_cert_path = os.environ.get("PEHCHAAN_UIDAI_CERT_PATH")
    if env_cert_path and has_cert(Path(env_cert_path)):
        cert_path = Path(env_cert_path)
        print(f"using UIDAI certificate at {cert_path} (from PEHCHAAN_UIDAI_CERT_PATH)")
    elif has_cert(REAL_CERTS):
        cert_path = REAL_CERTS
        print(f"real UIDAI certificate found in {REAL_CERTS} — real Aadhaar signatures will verify")
    else:
        cert_path = SAMPLES / "certs"
        print(f"no real certificate yet ({REAL_CERTS} is empty) — using the test certificate for demo cards")

    os.environ.update(
        {
            "PEHCHAAN_ENV": "dev",
            "PEHCHAAN_API_KEYS": f"{KEY}:hackingly:admin",
            "PEHCHAAN_DATA_DIR": str(DATA),
            "PEHCHAAN_DEMO_SAMPLES_DIR": str(SAMPLES),
            "PEHCHAAN_WEB_DIST": str(WEB),
            "PEHCHAAN_OCR_PROVIDER": os.environ.get("PEHCHAAN_OCR_PROVIDER") or "rapidocr",
            "PEHCHAAN_UIDAI_CERT_PATH": str(cert_path),
            "PEHCHAAN_PUBLIC_BASE_URL": f"http://localhost:{args.port}",
        }
    )

    import uvicorn

    print(f"\n  Pehchaan demo -> http://localhost:{args.port}    (API key: {KEY})")
    print(f"  cards: {SAMPLES}")
    if os.environ.get("PEHCHAAN_LLM_PROVIDER") == "groq" and os.environ.get("PEHCHAAN_GROQ_API_KEY"):
        print("  copilot: LLM (Groq)")
    else:
        print("  copilot: rules-based (add PEHCHAAN_GROQ_API_KEY to api/.env for LLM summaries)")
    print()
    uvicorn.run("pehchaan.main:app_factory", factory=True, host="127.0.0.1", port=args.port, log_level="warning")
    return 0


if __name__ == "__main__":
    sys.exit(main())
