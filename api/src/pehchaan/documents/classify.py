"""Deterministic document-type classification from anchor text."""

from __future__ import annotations

import re

from pehchaan.domain.models import DocType

# (pattern, weight). Patterns run on upper-cased text; \s* tolerates OCR dropping spaces.
ANCHORS: dict[DocType, list[tuple[re.Pattern[str], int]]] = {
    DocType.AADHAAR: [
        (re.compile(r"UNIQUE\s*IDENTIFICATION\s*AUTHORITY"), 3),
        (re.compile(r"AADHAA?R"), 3),
        (re.compile(r"(?<!\d)\d{4}\s?\d{4}\s?\d{4}(?!\s?\d)"), 2),
        (re.compile(r"[X*]{4}\s?[X*]{4}\s?\d{4}"), 2),
        (re.compile(r"YEAR\s*OF\s*BIRTH"), 2),
        (re.compile(r"GOVERNMENT\s*OF\s*INDIA"), 1),
        (re.compile(r"(?<![A-Z])VID\s*:?"), 1),
        # Weak front-of-card layout cues: abbreviated DOB label and a bare gender line
        (re.compile(r"(?<![A-Z])DOB\s*[:/]"), 1),
        (re.compile(r"(?m)^\s*(?:MALE|FEMALE|TRANSGENDER)\s*$"), 1),
    ],
    DocType.PAN: [
        (re.compile(r"INCOME\s*TAX\s*DEPARTMENT"), 3),
        (re.compile(r"PERMANENT\s*ACCOUNT\s*NUMBER"), 3),
        (re.compile(r"(?<![A-Z0-9])[A-Z]{3}[PCHFATBLJG][A-Z]\d{4}[A-Z](?![A-Z0-9])"), 2),
        (re.compile(r"GOVT\.?\s*OF\s*INDIA"), 1),
    ],
    DocType.VOTER_ID: [
        (re.compile(r"ELECTION\s*COMMISSION"), 3),
        (re.compile(r"ELECTOR"), 2),
        (re.compile(r"(?<![A-Z0-9])[A-Z]{3}\d{7}(?![A-Z0-9])"), 1),
    ],
    DocType.PASSPORT: [
        (re.compile(r"P<IND"), 4),
        (re.compile(r"PASSPORT"), 2),
        (re.compile(r"REPUBLIC\s*OF\s*INDIA"), 2),
    ],
    DocType.DRIVING_LICENCE: [
        (re.compile(r"DRIVING\s*LICEN[CS]E"), 3),
        (re.compile(r"(?<![A-Z])DL\s*NO"), 2),
        (re.compile(r"TRANSPORT"), 1),
    ],
    DocType.COLLEGE_ID: [
        (re.compile(r"COLLEGE|UNIVERSITY|INSTITUTE\s*OF|POLYTECHNIC|VIDYALAYA|VIDYAPEETH"), 2),
        (re.compile(r"STUDENT"), 2),
        (re.compile(r"ROLL\s*NO|ENROLL?MENT\s*NO|(?<![A-Z])USN(?![A-Z])|REG(ISTRATION)?\.?\s*NO"), 1),
        (re.compile(r"VALID\s*(UP\s*TO|UPTO|TILL|THRU|THROUGH|UNTIL)|VALIDITY"), 1),
        (re.compile(r"IDENTITY\s*CARD|I\.?D\.?\s*CARD"), 1),
        (re.compile(r"PRINCIPAL|REGISTRAR|COURSE|BRANCH|SEMESTER"), 1),
    ],
}

MIN_SCORE = 3


def classify(text: str) -> tuple[DocType, dict[DocType, int]]:
    upper = text.upper()
    scores = {
        doc_type: sum(weight for pattern, weight in anchors if pattern.search(upper))
        for doc_type, anchors in ANCHORS.items()
    }
    best = max(scores, key=lambda d: scores[d])
    return (best if scores[best] >= MIN_SCORE else DocType.UNKNOWN), scores
