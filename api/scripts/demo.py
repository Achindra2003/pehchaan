"""One command for the demo: fresh data, demo cards, API and UI on http://localhost:8000.

    uv run python scripts/demo.py            # build the web app first: cd web && npm run build
    uv run python scripts/demo.py --keep     # keep earlier registrations (duplicates will fire)

Uses the TEST certificate that signs the demo cards. Point PEHCHAAN_UIDAI_CERT_PATH at the real UIDAI
certificate when demoing with real Aadhaar cards.
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
KEY = "demo-key"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--keep", action="store_true", help="keep earlier registrations")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()

    if not (SAMPLES / "samples.json").exists():
        print("making the demo cards…")
        os.system(f'"{sys.executable}" "{API / "scripts" / "make_demo_samples.py"}"')  # noqa: S605 - fixed path
    if not args.keep:
        shutil.rmtree(DATA, ignore_errors=True)
        print("fresh demo data (duplicate history cleared)")
    if not WEB.is_dir():
        print(f"! no web build at {WEB}: run `npm run build` in web/ to serve the UI from this port")

    os.environ.update(
        {
            "PEHCHAAN_ENV": "dev",
            "PEHCHAAN_API_KEYS": f"{KEY}:hackingly:admin",
            "PEHCHAAN_DATA_DIR": str(DATA),
            "PEHCHAAN_DEMO_SAMPLES_DIR": str(SAMPLES),
            "PEHCHAAN_WEB_DIST": str(WEB),
            "PEHCHAAN_OCR_PROVIDER": os.environ.get("PEHCHAAN_OCR_PROVIDER", "rapidocr"),
            "PEHCHAAN_UIDAI_CERT_PATH": os.environ.get("PEHCHAAN_UIDAI_CERT_PATH", str(SAMPLES / "certs")),
            "PEHCHAAN_PUBLIC_BASE_URL": f"http://localhost:{args.port}",
        }
    )

    import uvicorn

    print(f"\n  Pehchaan demo -> http://localhost:{args.port}    (API key: {KEY})")
    print(f"  cards: {SAMPLES}\n")
    uvicorn.run("pehchaan.main:app_factory", factory=True, host="127.0.0.1", port=args.port, log_level="warning")
    return 0


if __name__ == "__main__":
    sys.exit(main())
