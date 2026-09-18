"""Demo-only endpoints: the specimen cards, served so a demo needs no file picker.

Mounted only outside production and only when the cards exist. They are synthetic SPECIMEN documents signed
with a local TEST key; nothing here touches real identity data.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Request, Response, status

demo = APIRouter(prefix="/demo", tags=["demo"])
MEDIA = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png", ".pdf": "application/pdf"}


def samples_dir(request: Request) -> Path:
    directory: Path = request.app.state.settings.demo_samples_dir
    if not (directory / "samples.json").exists():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No demo cards; run scripts/make_demo_samples.py")
    return directory


@demo.get("/samples")
async def list_samples(request: Request) -> list[dict[str, Any]]:
    return json.loads((samples_dir(request) / "samples.json").read_text(encoding="utf-8"))


@demo.get("/samples/{filename}")
async def get_sample(filename: str, request: Request) -> Response:
    directory = samples_dir(request)
    path = (directory / filename).resolve()
    if path.parent != directory.resolve() or not path.is_file() or path.suffix.lower() not in MEDIA:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Unknown demo card")
    return Response(path.read_bytes(), media_type=MEDIA[path.suffix.lower()])
