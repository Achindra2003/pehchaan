"""Institution checks for student-only events: AISHE registry lookup and college email domains."""

from __future__ import annotations

import csv
import logging
import re
from pathlib import Path

logger = logging.getLogger(__name__)

PERSONAL_EMAIL = {"gmail", "googlemail", "yahoo", "outlook", "hotmail", "live", "icloud", "proton", "protonmail", "rediffmail", "zoho"}  # fmt: skip
FILLER = {"of", "and", "the", "for", "in", "at"}
NAME_COLUMNS = ("name", "college name", "institution name", "name of the institution", "college_name")


def _normalise(name: str) -> str:
    return " ".join(w for w in re.findall(r"[a-z0-9]+", name.lower()) if w not in FILLER)


class InstitutionRegistry:
    def __init__(self, names: list[str]) -> None:
        self._names = {_normalise(n) for n in names if n}

    @classmethod
    def load(cls, path: Path) -> InstitutionRegistry:
        if not path.exists():
            return cls([])
        with path.open(encoding="utf-8", errors="ignore", newline="") as handle:
            reader = csv.DictReader(handle)
            column = next((c for c in reader.fieldnames or [] if c.strip().lower() in NAME_COLUMNS), None)
            if column is None:
                logger.warning("no institution name column in %s", path)
                return cls([])
            names = [row[column] for row in reader]
        logger.info("loaded %d institutions", len(names))
        return cls(names)

    @property
    def available(self) -> bool:
        return bool(self._names)

    def contains(self, institution: str) -> bool:
        target = _normalise(institution)
        return any(target == name or target in name or name in target for name in self._names if len(name) > 8)


def email_matches_institution(email: str | None, institution: str | None) -> bool:
    if not email or "@" not in email or not institution:
        return False
    labels = email.rsplit("@", 1)[1].lower().split(".")
    org = labels[0]
    if org in PERSONAL_EMAIL or len(org) < 2:
        return False
    words = [w for w in re.findall(r"[a-z]+", institution.lower()) if w not in FILLER]
    initials = "".join(w[0] for w in words)
    compact = "".join(words)
    return org == initials or org in compact or (len(org) >= 3 and initials.startswith(org))
