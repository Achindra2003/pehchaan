"""Field extraction from OCR lines, per document type. Deterministic and explainable."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date

from stdnum.in_ import aadhaar as aadhaar_number
from stdnum.in_ import epic as epic_number
from stdnum.in_ import pan as pan_number

from pehchaan.documents.dates import fix_digits, parse_date
from pehchaan.domain.models import DocType, ExtractedFields, FieldSource
from pehchaan.ocr.base import Box, OcrLine, OcrResult

STOPWORDS = {
    "ACCOUNT", "ADDRESS", "AADHAAR", "AADHAR", "AUTHORITY", "BIRTH", "BLOOD", "BRANCH", "CARD", "COLLEGE",
    "COMMISSION", "COURSE", "DATE", "DEPARTMENT", "DEPT", "DOB", "DOWNLOAD", "DRIVING", "ELECTION", "ELECTOR",
    "ENROLMENT", "ENROLLMENT", "FATHER", "FATHERS", "FEMALE", "GENDER", "GOVERNMENT", "GOVT", "GROUP", "HOLDER",
    "IDENTIFICATION", "IDENTITY", "INCOME", "INDIA", "INSTITUTE", "ISSUE", "LICENCE", "LICENSE", "MALE", "MERA",
    "MERI", "MOBILE", "NAME", "NUMBER", "PASSPORT", "PEHCHAAN", "PERMANENT", "PRINCIPAL", "REGISTRAR", "REPUBLIC",
    "ROLL", "SEX", "SIGNATURE", "SPECIMEN", "STUDENT", "TAX", "TRANSGENDER", "TRANSPORT", "UIDAI", "UNIQUE",
    "UNIVERSITY", "UPTO", "VALID", "VALIDITY", "VID", "YEAR",
}  # fmt: skip
LONG_STOPWORDS = {word for word in STOPWORDS if len(word) >= 5}

NAME_LABEL = re.compile(
    r"^[^A-Za-z]*(?:STUDENT'?S?\s*NAME|NAME\s*OF\s*(?:THE\s*)?(?:STUDENT|HOLDER|CANDIDATE)|ELECTOR'?S?\s*NAME|NAME)\s*[:.\-]?\s*(.*)$",
    re.I,
)
DOB_LABEL = re.compile(r"D\.?\s*O\.?\s*B\.?|DATE\s*OF\s*BIRTH|BIRTH\s*DATE|जन्म\s*तिथि", re.I)
YOB = re.compile(r"(?:YEAR\s*OF\s*BIRTH|(?<![A-Z])YOB)\s*[:.\-/]?\s*(\d{4})", re.I)
GENDER = re.compile(r"(?<![A-Z])(FEMALE|MALE|TRANSGENDER)(?![A-Z])", re.I)
AADHAAR = re.compile(r"(?<!\d)(\d{4})\s?(\d{4})\s?(\d{4})(?!\s?\d)")
AADHAAR_MASKED = re.compile(r"(?:[X*]{4}\s?){2}(\d{4})(?!\s?\d)", re.I)
TEN_ALNUM = re.compile(r"(?<![A-Z0-9])[A-Z0-9]{10}(?![A-Z0-9])")
DRIVING_LICENCE = re.compile(r"(?<![A-Z0-9])([A-Z]{2})[-\s]?(\d{2})[-\s]?(\d{4})[-\s]?(\d{7})(?!\d)")
ROLL = re.compile(
    r"(?:ROLL|ENROLL?MENT|REG(?:ISTRATION)?|ADMISSION|USN|STUDENT\s*ID|ID)\s*(?:NO\.?|NUMBER|#)?\s*[:.\-]\s*([A-Z0-9][A-Z0-9/\-]{3,19})",
    re.I,
)
INSTITUTION = re.compile(
    r"COLLEGE|UNIVERSITY|INSTITUTE|INSTITUTION|SCHOOL|VIDYALAYA|VIDYAPEETH|ACADEMY|POLYTECHNIC|(?<![A-Z])(IIT|NIT|IIIT|IISC)(?![A-Z])",
    re.I,
)
VALIDITY_LABEL = re.compile(
    r"VALID\s*(?:UP\s*TO|UPTO|TILL|THRU|THROUGH|UNTIL)|VALIDITY|DATE\s*OF\s*EXPIRY|EXPIRY(?:\s*DATE)?|EXPIRES(?:\s*ON)?",
    re.I,
)
HEADER = re.compile(r"INCOME\s*TAX|GOVT|GOVERNMENT|ELECTION\s*COMMISSION|DEPARTMENT", re.I)

LETTER_FOR_DIGIT = str.maketrans({"0": "O", "1": "I", "2": "Z", "5": "S", "8": "B", "6": "G"})
DIGIT_FOR_LETTER = str.maketrans(
    {"O": "0", "D": "0", "Q": "0", "I": "1", "L": "1", "Z": "2", "S": "5", "B": "8", "G": "6"}
)


@dataclass
class _Found:
    value: object
    line: OcrLine


@dataclass
class _Fields:
    found: dict[str, _Found] = field(default_factory=dict)

    def set(self, key: str, value: object, line: OcrLine) -> None:
        if value is not None and key not in self.found:
            self.found[key] = _Found(value, line)

    def get(self, key: str) -> object | None:
        return self.found[key].value if key in self.found else None


def extract_fields(ocr: OcrResult, doc_type: DocType) -> ExtractedFields:
    lines = ocr.lines
    f = _Fields()

    if doc_type is DocType.PASSPORT:
        _mrz(lines, f)
    _labelled_name(lines, f)
    _dob(lines, f, doc_type)
    _gender(lines, f)

    match doc_type:
        case DocType.AADHAAR:
            _aadhaar_number(lines, f)
            _name_near(lines, f, anchor=lambda t: bool(DOB_LABEL.search(t) or YOB.search(t) or GENDER.search(t)))
        case DocType.PAN:
            _pattern_number(lines, f, "LLLLLDDDDL", pan_number.is_valid)
            _name_after_header(lines, f)
        case DocType.VOTER_ID:
            _pattern_number(lines, f, "LLLDDDDDDD", epic_number.is_valid)
        case DocType.DRIVING_LICENCE:
            for line in lines:
                if m := DRIVING_LICENCE.search(fix_digits(line.text.upper())):
                    f.set("id_number", "".join(m.groups()), line)
                    break
        case DocType.COLLEGE_ID:
            _college(lines, f)
        case _:
            pass

    if doc_type in {DocType.COLLEGE_ID, DocType.DRIVING_LICENCE, DocType.PASSPORT, DocType.UNKNOWN}:
        _validity(lines, f)
    if "name" not in f.found:
        _tallest_name(lines, f)

    _apply_queries(ocr, f)

    dob = f.get("dob")
    yob = f.get("year_of_birth")
    return ExtractedFields(
        doc_type=doc_type,
        name=f.get("name"),  # type: ignore[arg-type]
        dob=dob,  # type: ignore[arg-type]
        year_of_birth=yob if dob is None else None,  # type: ignore[arg-type]
        gender=f.get("gender"),  # type: ignore[arg-type]
        id_number=f.get("id_number"),  # type: ignore[arg-type]
        institution=f.get("institution"),  # type: ignore[arg-type]
        valid_until=f.get("valid_until"),  # type: ignore[arg-type]
        dob_source=FieldSource.OCR if (dob or yob) else None,
        confidence={key: round(found.line.confidence, 3) for key, found in f.found.items()},
        boxes={key: found.line.box for key, found in f.found.items()},
    )


# --- names -------------------------------------------------------------------


def clean_name(text: str) -> str | None:
    text = re.sub(r"[^A-Za-z .']", " ", text)
    text = re.sub(r"\s+", " ", text).strip(" .'")
    letters = re.sub(r"[^A-Za-z]", "", text)
    if not 3 <= len(text) <= 48 or len(letters) < 3:
        return None
    for token in (t.upper().strip(".'") for t in text.split()):
        # OCR often glues header words together ("GOVERNMENTOFINDIA"), so check long tokens for substrings.
        if token in STOPWORDS or (len(token) > 10 and any(word in token for word in LONG_STOPWORDS)):
            return None
    return text


def _labelled_name(lines: list[OcrLine], f: _Fields) -> None:
    for i, line in enumerate(lines):
        m = NAME_LABEL.match(line.text)
        if not m:
            continue
        if name := clean_name(m[1]):
            f.set("name", name, line)
            return
        if not m[1].strip() and i + 1 < len(lines) and (name := clean_name(lines[i + 1].text)):
            f.set("name", name, lines[i + 1])
            return


def _name_near(lines: list[OcrLine], f: _Fields, anchor) -> None:
    for i, line in enumerate(lines):
        if not anchor(line.text):
            continue
        for j in range(i - 1, max(-1, i - 4), -1):
            if name := clean_name(lines[j].text):
                f.set("name", name, lines[j])
                return


def _name_after_header(lines: list[OcrLine], f: _Fields) -> None:
    seen_header = False
    for line in lines:
        if HEADER.search(line.text):
            seen_header = True
            continue
        if seen_header and (name := clean_name(line.text)):
            f.set("name", name, line)
            return


def _tallest_name(lines: list[OcrLine], f: _Fields) -> None:
    candidates = [(line.height, name, line) for line in lines if (name := clean_name(line.text))]
    if candidates:
        _, name, line = max(candidates, key=lambda c: c[0])
        f.set("name", name, line)


# --- dates and gender ----------------------------------------------------------


def _dob(lines: list[OcrLine], f: _Fields, doc_type: DocType) -> None:
    for i, line in enumerate(lines):
        if m := YOB.search(fix_digits(line.text)):
            f.set("year_of_birth", int(m[1]), line)
        if m := DOB_LABEL.search(line.text):
            if d := parse_date(line.text[m.end() :]):
                f.set("dob", d, line)
                return
            if i + 1 < len(lines) and (d := parse_date(lines[i + 1].text)):
                f.set("dob", d, lines[i + 1])
                return
    if doc_type is DocType.PAN:  # the only date printed on a PAN card is the date of birth
        for line in lines:
            if d := parse_date(line.text):
                f.set("dob", d, line)
                return


def _gender(lines: list[OcrLine], f: _Fields) -> None:
    for line in lines:
        if m := GENDER.search(line.text):
            f.set("gender", m[1].upper()[0], line)
            return


def _validity(lines: list[OcrLine], f: _Fields) -> None:
    for i, line in enumerate(lines):
        if m := VALIDITY_LABEL.search(line.text):
            if d := parse_date(line.text[m.end() :], month_year_ok=True):
                f.set("valid_until", d, line)
                return
            if i + 1 < len(lines) and (d := parse_date(lines[i + 1].text, month_year_ok=True)):
                f.set("valid_until", d, lines[i + 1])
                return


# --- numbers -----------------------------------------------------------------------


def _aadhaar_number(lines: list[OcrLine], f: _Fields) -> None:
    candidates: list[tuple[bool, float, str, OcrLine]] = []
    for line in lines:
        if re.search(r"(?<![A-Z])VID", line.text, re.I):
            continue
        text = fix_digits(line.text)
        for m in AADHAAR.finditer(text):
            number = "".join(m.groups())
            candidates.append((aadhaar_number.is_valid(number), line.height, number, line))
        for m in AADHAAR_MASKED.finditer(text):
            candidates.append((True, line.height, f"XXXXXXXX{m[1]}", line))
    if candidates:
        _, _, number, line = max(candidates, key=lambda c: (c[0], c[1]))
        f.set("id_number", number, line)


def _pattern_number(lines: list[OcrLine], f: _Fields, shape: str, is_valid) -> None:
    """Find an ID shaped like `shape` (L=letter, D=digit), repairing OCR letter/digit swaps by position."""
    for line in lines:
        for token in TEN_ALNUM.findall(re.sub(r"[\s\-]", "", line.text.upper())):
            repaired = "".join(
                ch.translate(LETTER_FOR_DIGIT) if kind == "L" else ch.translate(DIGIT_FOR_LETTER)
                for ch, kind in zip(token, shape, strict=True)
            )
            if is_valid(repaired):
                f.set("id_number", repaired, line)
                return


def _college(lines: list[OcrLine], f: _Fields) -> None:
    for line in lines:
        if INSTITUTION.search(line.text) and len(line.text.strip()) >= 6:
            f.set("institution", re.sub(r"\s+", " ", line.text).strip(), line)
            break
    for line in lines:
        if m := ROLL.search(line.text):
            f.set("id_number", m[1].upper(), line)
            break


def _mrz(lines: list[OcrLine], f: _Fields) -> None:
    mrz = [re.sub(r"\s", "", line.text.upper()).replace("«", "<") for line in lines if "<<" in line.text]
    first = next((m for m in mrz if m.startswith("P<")), None)
    second = next((m for m in mrz if not m.startswith("P<") and len(m) >= 28), None)
    anchor = next(line for line in lines if "<<" in line.text) if mrz else None
    if first and anchor:
        surname, _, given = first[5:].partition("<<")
        name = f"{given.replace('<', ' ').strip()} {surname.replace('<', ' ').strip()}".strip()
        if cleaned := clean_name(name):
            f.set("name", cleaned, anchor)
    if second and anchor and _mrz_check(second[0:9], second[9]) and _mrz_check(second[13:19], second[19]):
        f.set("id_number", second[0:9].replace("<", ""), anchor)
        yy, mm, dd = int(second[13:15]), int(second[15:17]), int(second[17:19])
        century = 1900 if yy > date.today().year % 100 else 2000
        try:
            f.set("dob", date(century + yy, mm, dd), anchor)
        except ValueError:
            pass


def _mrz_check(field_text: str, check: str) -> bool:
    weights = (7, 3, 1)
    total = 0
    for i, ch in enumerate(field_text):
        value = int(ch) if ch.isdigit() else (ord(ch) - 55 if ch.isalpha() else 0)
        total += value * weights[i % 3]
    return check.isdigit() and total % 10 == int(check)


def _apply_queries(ocr: OcrResult, f: _Fields) -> None:
    q = ocr.queries
    if "NAME" in q and (name := clean_name(q["NAME"].text)):
        f.set("name", name, q["NAME"])
    if "DOB" in q and (d := parse_date(q["DOB"].text)):
        f.set("dob", d, q["DOB"])
    if "ID_NUMBER" in q:
        f.set("id_number", re.sub(r"\s", "", q["ID_NUMBER"].text.upper()), q["ID_NUMBER"])
    if "INSTITUTION" in q:
        f.set("institution", q["INSTITUTION"].text.strip(), q["INSTITUTION"])
    if "VALID_UNTIL" in q and (d := parse_date(q["VALID_UNTIL"].text, month_year_ok=True)):
        f.set("valid_until", d, q["VALID_UNTIL"])


def missing_queries(fields: ExtractedFields) -> list[str]:
    wanted = {"NAME": fields.name, "DOB": fields.dob or fields.year_of_birth, "ID_NUMBER": fields.id_number}
    if fields.doc_type is DocType.COLLEGE_ID:
        wanted |= {"INSTITUTION": fields.institution, "VALID_UNTIL": fields.valid_until}
        wanted.pop("DOB")
    return [alias for alias, value in wanted.items() if not value]


__all__ = ["Box", "clean_name", "extract_fields", "missing_queries"]
