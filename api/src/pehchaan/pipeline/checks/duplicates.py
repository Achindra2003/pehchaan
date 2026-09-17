from __future__ import annotations

import asyncio
import logging
import re

import cv2
import numpy as np
import pdqhash

from pehchaan.domain.models import CheckResult, CheckStatus, Finding
from pehchaan.names import APPROVE_AT, name_score
from pehchaan.pipeline.checks.base import Check, finding
from pehchaan.pipeline.context import VerificationContext
from pehchaan.security import Crypto
from pehchaan.store.sqlite import Store
from pehchaan.vision.faces import FaceEngine

logger = logging.getLogger(__name__)

PDQ_SAME_IMAGE = 6  # bits out of 256: effectively the same photo, re-saved or cropped
FACE_SAME_PERSON = 0.6  # stricter than SFace's 0.363 because ID photos are small and we flag strangers
DEVICE_MANY_IDENTITIES = 3


class DuplicatesCheck(Check):
    """Platform-wide: has this ID, image, face or device been seen under a different identity?

    Conflicts go to review for both registrations; nobody is rejected for a duplicate.
    """

    name = "duplicates"

    def __init__(self, store: Store, crypto: Crypto, faces: FaceEngine | None) -> None:
        self._store = store
        self._crypto = crypto
        self._faces = faces

    async def run(self, ctx: VerificationContext) -> CheckResult:
        try:
            return await asyncio.to_thread(self._run, ctx)
        except Exception as exc:
            logger.error("duplicate index unavailable: %s", type(exc).__name__)
            return self.result(CheckStatus.ERROR, finding("DUPLICATE_INDEX_UNAVAILABLE"))

    def _run(self, ctx: VerificationContext) -> CheckResult:
        keys = ctx.index_keys
        form_name = ctx.payload.form.name
        exclude = (ctx.payload.event_id, ctx.payload.registration_id)
        fields = ctx.fields

        number = re.sub(r"[^A-Z0-9]", "", (fields.id_number or "").upper())
        if number and not number.startswith("XXXX"):
            keys.id_hashes.append(self._crypto.id_hash(f"{fields.doc_type.value}:{number}"))
        if ctx.qr is not None and ctx.qr.reference_id and ctx.qr_certificate:
            keys.id_hashes.append(self._crypto.id_hash(f"aadhaar_ref:{ctx.qr.reference_id}"))
        if ctx.payload.device_id:
            keys.device_hash = self._crypto.id_hash(f"device:{ctx.payload.device_id}")
        if ctx.image is not None:
            vector, _quality = pdqhash.compute(cv2.cvtColor(ctx.image, cv2.COLOR_BGR2RGB))
            keys.pdq = f"{int(''.join(str(int(b)) for b in vector), 2):064x}"
        if self._faces is not None and ctx.image is not None and ctx.id_faces:
            ctx.id_face_embedding = self._faces.embed(ctx.image, ctx.id_faces[0])
            keys.face = ctx.id_face_embedding

        findings: list[Finding] = []
        conflicts: set[str] = set()
        same_person = False

        for match in self._store.find_by_keys("id", keys.id_hashes, exclude):
            if name_score(form_name, match.name) >= APPROVE_AT:
                same_person = True
            else:
                conflicts.add(match.verification_id)
        if conflicts:
            findings.append(finding("DUPLICATE_ID_OTHER_IDENTITY"))

        if keys.pdq:
            image_conflicts = {
                m.verification_id
                for m in self._store.find_similar_images(keys.pdq, PDQ_SAME_IMAGE, exclude)
                if name_score(form_name, m.name) < APPROVE_AT
            }
            if image_conflicts:
                findings.append(finding("DUPLICATE_IMAGE"))
                conflicts |= image_conflicts

        if keys.face is not None:
            face_conflicts = {
                match.verification_id
                for match, their_ids in self._store.find_similar_faces(keys.face, FACE_SAME_PERSON, exclude)
                if not set(their_ids) & set(keys.id_hashes) and name_score(form_name, match.name) < APPROVE_AT
            }
            if face_conflicts:
                findings.append(finding("DUPLICATE_FACE_OTHER_IDENTITY"))
                conflicts |= face_conflicts

        if keys.device_hash:
            names = {m.name.lower() for m in self._store.find_by_keys("device", [keys.device_hash], exclude)}
            others = {n for n in names if name_score(form_name, n) < APPROVE_AT}
            if len(others) >= DEVICE_MANY_IDENTITIES:
                findings.append(finding("DEVICE_SHARED_BY_MANY", count=len(others) + 1))

        if same_person and not findings:
            findings.append(finding("SAME_PERSON_KNOWN"))
        ctx.conflicts = sorted(conflicts)
        status = CheckStatus.WARN if any(f.code != "SAME_PERSON_KNOWN" for f in findings) else CheckStatus.PASS
        return self.result(status, *findings, keys_checked=len(keys.id_hashes), face_indexed=keys.face is not None)


def pdq_distance(a: str, b: str) -> int:
    return (int(a, 16) ^ int(b, 16)).bit_count()


__all__ = ["DuplicatesCheck", "np", "pdq_distance"]
