"""Generate the demo cards (SPECIMEN, test-signed) as a fallback if real IDs misbehave on the day.

    uv run python scripts/make_demo_samples.py [--out demo-samples]

Writes: genuine.jpg, edited-dob.jpg, reused-id.jpg, blurry.jpg, no-qr.jpg, college-id.jpg and a README
listing the form values to type during the demo, plus certs/ holding the TEST signing certificate.
"""

from __future__ import annotations

import argparse
import random
from datetime import date
from pathlib import Path

from pehchaan import specimens as sp

FORMS: list[str] = []


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default="demo-samples")
    out = Path(parser.parse_args().out)
    (out / "certs").mkdir(parents=True, exist_ok=True)
    key = sp.make_test_signing_key(out / "certs")
    rng = random.Random(2026)

    asha = sp.make_person(rng, dob=date(2003, 4, 12), gender="F")
    card = sp.render_aadhaar(asha, qr_payload=sp.secure_qr_for(asha, key))
    _write(out, "genuine.jpg", sp.photograph(card, rng), asha.name, asha.dob, "verified at L3 in about 2 seconds")
    _write(out, "reused-id.jpg", sp.photograph(card, rng), "Rohit Verma", asha.dob, "same ID, different name: both registrations go to review")  # fmt: skip
    _write(out, "blurry.jpg", sp.photograph(card, rng, blur=4), asha.name, asha.dob, "retake asked, nobody rejected")

    kid = sp.make_person(rng, dob=date(2010, 3, 5), gender="M")
    edited = sp.paste_edit(
        sp.render_aadhaar(kid, qr_payload=sp.secure_qr_for(kid, key)), (290, 212, 640, 262), "DOB: 05/03/2004", 36
    )
    _write(out, "edited-dob.jpg", sp.photograph(edited, rng), kid.name, date(2004, 3, 5), "not eligible: printed DOB contradicts the signed QR")  # fmt: skip

    hidden = sp.make_person(rng, dob=date(2009, 7, 7), gender="M")
    no_qr = sp.paste_edit(sp.render_aadhaar(hidden, qr_payload=None), (290, 212, 640, 262), "DOB: 07/07/2003", 36)
    _write(out, "no-qr.jpg", sp.photograph(no_qr, rng), hidden.name, date(2003, 7, 7), "QR hidden: one retake, then a human reviews")  # fmt: skip

    student = sp.make_person(rng, dob=date(2004, 8, 9), gender="F")
    college = sp.render_college_id(
        student, institution="Specimen Institute of Technology", roll="1SI22CS042", valid_until=date(2027, 6, 30)
    )
    _write(out, "college-id.jpg", sp.photograph(college, rng), student.name, student.dob, "student-only event: verified at L2")  # fmt: skip

    (out / "README.md").write_text(
        "# Demo cards (synthetic SPECIMEN, signed with a TEST key)\n\n"
        "Point the API at the test certificate to make the signed-QR path work with these:\n\n"
        f"    PEHCHAAN_UIDAI_CERT_PATH={out.resolve() / 'certs'}\n\n"
        "| File | Type this name | Date of birth | What the judges see |\n|---|---|---|---|\n"
        + "\n".join(FORMS)
        + "\n\nReal IDs are always the better demo; these are the fallback.\n",
        encoding="utf-8",
    )
    print(f"wrote {len(FORMS)} demo cards to {out.resolve()}")


def _write(out: Path, name: str, image: bytes, form_name: str, dob: date, note: str) -> None:
    (out / name).write_bytes(image)
    FORMS.append(f"| {name} | {form_name} | {dob.isoformat()} | {note} |")


if __name__ == "__main__":
    main()
