"""Evaluate Pehchaan on synthetic SPECIMEN documents and write eval/results.md.

    cd api && uv run python ../eval/run.py

Every sample runs through the real pipeline (OCR, QR decoding, signature checks, duplicate index) in the
order listed, so duplicate attacks see the earlier genuine registrations. Metric names follow
ISO/IEC 30107-3 where they apply: APCER = attacks accepted as verified, BPCER = genuine people rejected.
"""

from __future__ import annotations

import io
import json
import random
import shutil
import statistics
import sys
from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient

from pehchaan import specimens as sp
from pehchaan.config import Settings
from pehchaan.main import create_app

ROOT = Path(__file__).resolve().parent
WORK = ROOT / "data" / "generated"
API_KEY = "eval-key"
HEADERS = {"X-API-Key": API_KEY}

ADULT = "ai-build-challenge-blr"
STUDENT = "campus-hack-students"
JUNIOR = "junior-coders-13-17"
OPEN = "open-meetup"
INSTITUTION = "Specimen Institute of Technology"


@dataclass
class Sample:
    sample_id: str
    event: str
    form: dict
    image: bytes
    media_type: str
    expected: str
    attack: str = "none"
    registration: str | None = None


def build(rng: random.Random, key: rsa.RSAPrivateKey) -> list[Sample]:
    samples: list[Sample] = []
    attacker_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)

    def add(sample_id, event, person_or_name, dob, image, expected, attack="none", media="image/jpeg", **form):
        name = person_or_name if isinstance(person_or_name, str) else person_or_name.name
        samples.append(
            Sample(
                sample_id,
                event,
                {"name": name, **({"dob": str(dob)} if dob else {}), **form},
                image,
                media,
                expected,
                attack,
            )
        )

    def aadhaar(person, **kw):
        return sp.render_aadhaar(person, qr_payload=sp.secure_qr_for(person, key), **kw)

    adults = [sp.make_person(rng) for _ in range(10)]
    for i, person in enumerate(adults):
        card = aadhaar(person, masked=i % 4 == 3, year_only=i == 5)
        add(f"g-aadhaar-{i:02d}", ADULT, person, person.dob, sp.photograph(card, rng), "verified")

    pdf_person = sp.make_person(rng)
    buffer = io.BytesIO()
    aadhaar(pdf_person).save(buffer, "PDF", resolution=150)
    add("g-eaadhaar-pdf", ADULT, pdf_person, pdf_person.dob, buffer.getvalue(), "verified", media="application/pdf")

    for i in range(4):
        person = sp.make_person(rng)
        add(
            f"g-pan-{i}",
            ADULT,
            person,
            person.dob,
            sp.photograph(sp.render_pan(person, sp.pan_for(person, rng)), rng),
            "verified",
        )

    for i in range(4):
        person = sp.make_person(rng, dob=date(rng.randint(2003, 2006), rng.randint(1, 12), rng.randint(1, 28)))
        card = sp.render_college_id(
            person, institution=INSTITUTION, roll=f"1SI2{i}CS0{rng.randint(10, 99)}", valid_until=date(2027, 6, 30)
        )
        email = {"email": f"{person.name.split()[0].lower()}@sit.edu.in"} if i % 2 == 0 else {}
        add(f"g-college-{i}", STUDENT, person, person.dob, sp.photograph(card, rng), "verified", **email)

    for i in range(3):
        person = sp.make_person(rng, dob=date(2011, rng.randint(1, 12), rng.randint(1, 28)))
        add(f"g-minor-{i}", JUNIOR, person, person.dob, sp.photograph(aadhaar(person), rng), "verified")

    initials = sp.make_person(rng)
    first, last = initials.name.split()
    # Initials on the form are genuine but ambiguous: the design sends them to a person, never rejects.
    add(
        "g-initials-form",
        ADULT,
        f"{first[0]}. {last}",
        initials.dob,
        sp.photograph(aadhaar(initials), rng),
        "needs_review",
    )

    # --- attacks ----------------------------------------------------------------------------------------
    for i in range(4):
        minor = sp.make_person(rng, dob=date(2010, rng.randint(1, 12), rng.randint(1, 28)))
        fake = minor.dob.replace(year=2003)
        edited = sp.paste_edit(aadhaar(minor), (290, 212, 640, 262), f"DOB: {fake.strftime('%d/%m/%Y')}", 36)
        add(f"a-edited-dob-{i}", ADULT, minor, fake, sp.photograph(edited, rng), "not_eligible", "edited_dob")

    for i in range(3):
        minor = sp.make_person(rng, dob=date(2009, rng.randint(1, 12), rng.randint(1, 28)))
        fake = minor.dob.replace(year=2002)
        edited = sp.paste_edit(
            sp.render_aadhaar(minor, qr_payload=None), (290, 212, 640, 262), f"DOB: {fake.strftime('%d/%m/%Y')}", 36
        )
        add(
            f"a-edited-dob-noqr-{i}",
            ADULT,
            minor,
            fake,
            sp.photograph(edited, rng),
            "action_required",
            "edited_dob_qr_hidden",
        )

    for i in range(3):
        owner = adults[i]
        impostor = sp.make_person(rng)
        add(
            f"a-reused-id-{i}",
            ADULT,
            impostor.name,
            owner.dob,
            sp.photograph(aadhaar(owner), rng),
            "needs_review",
            "reused_id_new_name",
        )

    for i in range(2):
        person = sp.make_person(rng)
        forged = sp.render_aadhaar(person, qr_payload=sp.secure_qr_for(person, attacker_key))
        add(
            f"a-forged-qr-{i}",
            ADULT,
            person,
            person.dob,
            sp.photograph(forged, rng),
            "needs_review",
            "forged_signature",
        )

    for i in range(2):
        donor, forger = sp.make_person(rng), sp.make_person(rng)
        pasted = sp.render_aadhaar(forger, qr_payload=sp.secure_qr_for(donor, key))
        add(
            f"a-transplanted-qr-{i}",
            ADULT,
            forger,
            forger.dob,
            sp.photograph(pasted, rng),
            "not_eligible",
            "qr_from_other_card",
        )

    for i in range(2):
        kid = sp.make_person(rng, dob=date(2010, rng.randint(1, 12), rng.randint(1, 28)))
        add(f"a-underage-{i}", ADULT, kid, kid.dob, sp.photograph(aadhaar(kid), rng), "not_eligible", "underage")

    adult_on_junior = sp.make_person(rng, dob=date(2006, 5, 5))
    add(
        "a-overage-junior",
        JUNIOR,
        adult_on_junior,
        adult_on_junior.dob,
        sp.photograph(aadhaar(adult_on_junior), rng),
        "not_eligible",
        "overage",
    )

    for i in range(2):
        person = sp.make_person(rng, dob=date(2004, rng.randint(1, 12), rng.randint(1, 28)))
        card = sp.render_college_id(
            person, institution=INSTITUTION, roll=f"1SI19CS0{rng.randint(10, 99)}", valid_until=date(2025, 6, 30)
        )
        add(
            f"a-expired-college-{i}",
            STUDENT,
            person,
            person.dob,
            sp.photograph(card, rng),
            "action_required",
            "expired_college_id",
        )

    wrong_doc = sp.make_person(rng)
    add(
        "a-aadhaar-student-event",
        STUDENT,
        wrong_doc,
        wrong_doc.dob,
        sp.photograph(aadhaar(wrong_doc), rng),
        "action_required",
        "no_student_proof",
    )

    for i in range(2):
        person = sp.make_person(rng)
        add(
            f"a-blurry-{i}",
            ADULT,
            person,
            person.dob,
            sp.photograph(aadhaar(person), rng, blur=4),
            "action_required",
            "blurry",
        )

    for i in range(2):
        person = sp.make_person(rng)
        bad = person.aadhaar[:-1] + str((int(person.aadhaar[-1]) + 1) % 10)
        fake = sp.Person(person.name, person.father, person.dob, person.gender, bad, person.reference_time)
        add(
            f"a-invalid-number-{i}",
            OPEN,
            fake,
            fake.dob,
            sp.photograph(sp.render_aadhaar(fake, qr_payload=None), rng),
            "needs_review",
            "invalid_id_number",
        )

    return samples


def run() -> int:
    shutil.rmtree(WORK, ignore_errors=True)
    (WORK / "certs").mkdir(parents=True)
    rng = random.Random(2026)
    key = sp.make_test_signing_key(WORK / "certs")
    samples = build(rng, key)

    settings = Settings(
        env="test",
        api_keys=API_KEY,
        data_dir=WORK / "db",
        uidai_cert_path=WORK / "certs",
        ocr_provider="rapidocr",
        seed_demo=True,
        web_dist=WORK / "no-web",
    )
    rows = []
    with TestClient(create_app(settings)) as client:
        client.put(f"/v1/events/{OPEN}/policy", json={"event_date": "2026-09-18"}, headers=HEADERS)
        warmup = sp.photograph(sp.render_pan(sp.make_person(random.Random(1)), "WARMP0000W"), random.Random(1))
        client.post("/v1/verifications", data={"payload": json.dumps({"registration_id": "warmup", "event_id": OPEN, "form": {"name": "Warm Up"}})}, files={"id_image": ("w.jpg", warmup, "image/jpeg")}, headers=HEADERS)  # fmt: skip
        for sample in samples:
            body = {
                "registration_id": sample.registration or sample.sample_id,
                "event_id": sample.event,
                "form": sample.form,
            }
            response = client.post(
                "/v1/verifications",
                data={"payload": json.dumps(body)},
                files={"id_image": ("id", sample.image, sample.media_type)},
                headers=HEADERS,
            )
            result = response.json()
            rows.append((sample, result))
            mark = "ok " if result["decision"] == sample.expected else "XX "
            print(
                f"{mark}{sample.sample_id:28} expected={sample.expected:16} got={result['decision']:16} L{result['evidence_level']} {result['latency_ms']}ms"
            )
        audit = client.get("/v1/audit/integrity", headers=HEADERS).json()

    report = summarise(rows, audit)
    (ROOT / "results.md").write_text(report, encoding="utf-8")
    print("\n" + report)
    return 0


def summarise(rows: list[tuple[Sample, dict]], audit: dict) -> str:
    genuine = [(s, r) for s, r in rows if s.attack == "none"]
    attacks = [(s, r) for s, r in rows if s.attack != "none"]
    latencies = sorted(r["latency_ms"] for _, r in rows)

    def pct(n: int, d: int) -> str:
        return f"{100 * n / d:.0f}% ({n}/{d})" if d else "n/a"

    rejected = sum(r["decision"] == "not_eligible" for _, r in genuine)
    friction = sum(r["decision"] in {"needs_review", "action_required"} for _, r in genuine)
    auto = sum(r["decision"] == "verified" for _, r in genuine)
    accepted_attacks = sum(r["decision"] == "verified" for _, r in attacks)
    exact = sum(r["decision"] == s.expected for s, r in rows)

    by_attack: dict[str, list[dict]] = defaultdict(list)
    for sample, result in attacks:
        by_attack[sample.attack].append(result)

    lines = [
        "# Evaluation results",
        "",
        f"{len(rows)} synthetic SPECIMEN samples ({len(genuine)} genuine, {len(attacks)} attacks), local OCR (RapidOCR), "
        "Secure QR signed with a test key. Generated by `eval/run.py`; numbers are from synthetic data, "
        "not a substitute for Hackingly's anonymised samples.",
        "",
        "| Metric | Result |",
        "|---|---|",
        f"| Genuine participants rejected (BPCER) | **{pct(rejected, len(genuine))}** |",
        f"| Genuine participants auto-verified | {pct(auto, len(genuine))} |",
        f"| Genuine participants asked to retake or reviewed (friction) | {pct(friction, len(genuine))} |",
        f"| Attacks accepted as verified (APCER) | **{pct(accepted_attacks, len(attacks))}** |",
        f"| Decisions matching the expected outcome | {pct(exact, len(rows))} |",
        f"| Latency p50 / p95 (CPU, local OCR) | {latencies[len(latencies) // 2]} ms / {latencies[int(len(latencies) * 0.95)]} ms |",
        f"| Audit chain intact | {audit['intact']} ({audit['entries']} entries) |",
        "",
        "## Attacks",
        "",
        "| Attack | Samples | Stopped (not verified) | Outcomes |",
        "|---|---|---|---|",
    ]
    for attack, results in sorted(by_attack.items()):
        stopped = sum(r["decision"] != "verified" for r in results)
        outcomes = ", ".join(f"{d} ×{n}" for d, n in sorted(_count(r["decision"] for r in results).items()))
        lines.append(f"| {attack.replace('_', ' ')} | {len(results)} | {pct(stopped, len(results))} | {outcomes} |")

    lines += [
        "",
        "## Every sample",
        "",
        "| Sample | Expected | Got | Level | Confidence | Reasons |",
        "|---|---|---|---|---|---|",
    ]
    for sample, result in rows:
        codes = ", ".join(sorted({r["code"] for r in result["reasons"] if r["effect"] != "info"})) or "—"
        mark = "" if result["decision"] == sample.expected else " ⚠️"
        lines.append(
            f"| {sample.sample_id} | {sample.expected} | {result['decision']}{mark} | L{result['evidence_level']} | {result['confidence']} | {codes} |"
        )
    lines += [
        "",
        "## Not covered by this synthetic set",
        "",
        "- Face checks (photo swap, selfie mismatch, liveness): specimen cards carry no real faces.",
        "- Screen recapture: the moiré signal is reported but disabled until calibrated on real photos.",
        "- AI-generated cards without a Secure QR: handled by policy (QR required for age-restricted events), not by pixels.",
        "- Real phone photos and real UIDAI signatures: run the team's consented samples and Hackingly's anonymised set.",
    ]
    statistics.mean(latencies)  # keeps the import honest if the table changes
    return "\n".join(lines) + "\n"


def _count(values) -> dict[str, int]:
    counts: dict[str, int] = defaultdict(int)
    for value in values:
        counts[value] += 1
    return counts


if __name__ == "__main__":
    sys.exit(run())
