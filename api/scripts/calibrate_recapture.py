"""Calibrate the screen-photo (recapture) check on real photos, the only way it can honestly be set.

    uv run python scripts/calibrate_recapture.py --cards path/to/real-card-photos --screens path/to/screen-photos

Take 5-10 photos of physical cards and 5-10 photos of the same cards displayed on a laptop or phone screen.
The script prints both score ranges and, when they separate, the threshold to set:

    PEHCHAAN_RECAPTURE_CHECK_ENABLED=true
    (and MOIRE_THRESHOLD in pipeline/checks/tamper.py)

If the ranges overlap, leave the check disabled: a false "photo of a screen" costs a genuine participant a
retake, and a synthetic simulation of a screen does not reproduce real moire well enough to tune on.
"""

from __future__ import annotations

import argparse
import statistics
import sys
from pathlib import Path

from pehchaan.imaging import decode_image
from pehchaan.pipeline.checks.tamper import _moire_score

SUFFIXES = {".jpg", ".jpeg", ".png"}


def scores(directory: Path) -> list[tuple[str, float]]:
    files = sorted(p for p in directory.glob("*") if p.suffix.lower() in SUFFIXES)
    return [(p.name, _moire_score(decode_image(p.read_bytes()))) for p in files]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cards", type=Path, required=True, help="photos of physical cards")
    parser.add_argument("--screens", type=Path, required=True, help="photos of cards shown on a screen")
    args = parser.parse_args()

    cards, screens = scores(args.cards), scores(args.screens)
    if not cards or not screens:
        print("need photos in both folders")
        return 1

    for label, values in (("physical card", cards), ("screen photo", screens)):
        numbers = [v for _, v in values]
        print(
            f"\n{label}: n={len(numbers)} min={min(numbers):.2f} median={statistics.median(numbers):.2f} max={max(numbers):.2f}"
        )
        for name, value in values:
            print(f"   {value:6.2f}  {name}")

    highest_card = max(v for _, v in cards)
    lowest_screen = min(v for _, v in screens)
    print()
    if lowest_screen > highest_card:
        threshold = round((highest_card + lowest_screen) / 2, 2)
        print(f"separated: set MOIRE_THRESHOLD = {threshold} and PEHCHAAN_RECAPTURE_CHECK_ENABLED=true")
        print(f"  margin: cards up to {highest_card:.2f}, screens from {lowest_screen:.2f}")
    else:
        print("overlapping: leave the check disabled. A false retake costs more than this signal is worth.")
        print(f"  cards reach {highest_card:.2f}, screens start at {lowest_screen:.2f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
