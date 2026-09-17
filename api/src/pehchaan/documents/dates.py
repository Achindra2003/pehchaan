"""Date parsing tuned for Indian ID documents (day-first) and OCR noise."""

from __future__ import annotations

import calendar
import re
from datetime import date

MONTHS: dict[str, int] = {name.lower(): i for i, name in enumerate(calendar.month_abbr) if name}
MONTHS |= {name.lower(): i for i, name in enumerate(calendar.month_name) if name}
MONTHS["sept"] = 9

_DMY = re.compile(r"(?<!\d)(\d{1,2})\s*[/\-.]\s*(\d{1,2})\s*[/\-.]\s*(\d{4})(?!\d)")
_YMD = re.compile(r"(?<!\d)(\d{4})\s*[/\-.]\s*(\d{1,2})\s*[/\-.]\s*(\d{1,2})(?!\d)")
_TEXT_DMY = re.compile(r"(?<!\d)(\d{1,2})\s*[-/ .]?\s*([A-Za-z]{3,9})\s*[-/ .,]?\s*(\d{4})(?!\d)")
_MONTH_YEAR_TEXT = re.compile(r"(?<![A-Za-z])([A-Za-z]{3,9})\s*[-/ .,']?\s*(\d{4})(?!\d)")
_MONTH_YEAR_NUM = re.compile(r"(?<![\d/\-.])(\d{1,2})\s*[/\-.]\s*(\d{4})(?!\d)")
_CONFUSABLE = str.maketrans({"O": "0", "o": "0", "D": "0", "I": "1", "l": "1", "|": "1", "S": "5", "B": "8"})
_NUMERIC_RUN = re.compile(r"[\dOoDIl|SB/\-.]{6,}")


def fix_digits(text: str) -> str:
    """Undo common OCR letter-for-digit swaps inside numeric runs (e.g. '1O/O5/2OO4')."""

    def repair(match: re.Match[str]) -> str:
        run = match.group(0)
        return run.translate(_CONFUSABLE) if sum(ch.isdigit() for ch in run) >= 2 else run

    return _NUMERIC_RUN.sub(repair, text)


def find_dates(text: str) -> list[date]:
    text = fix_digits(text)
    found: list[tuple[int, date]] = []
    for m in _DMY.finditer(text):
        _add(found, m.start(), int(m[3]), int(m[2]), int(m[1]))
    for m in _YMD.finditer(text):
        _add(found, m.start(), int(m[1]), int(m[2]), int(m[3]))
    for m in _TEXT_DMY.finditer(text):
        if month := MONTHS.get(m[2].lower()):
            _add(found, m.start(), int(m[3]), month, int(m[1]))
    found.sort(key=lambda item: item[0])
    return [d for _, d in found]


def parse_date(text: str, *, month_year_ok: bool = False) -> date | None:
    """First full date in the text; optionally a month-year ('06/2027', 'Jun 2027') as its last day."""
    if dates := find_dates(text):
        return dates[0]
    if not month_year_ok:
        return None
    text = fix_digits(text)
    for m in _MONTH_YEAR_NUM.finditer(text):
        if result := _end_of_month(int(m[2]), int(m[1])):
            return result
    for m in _MONTH_YEAR_TEXT.finditer(text):
        if (month := MONTHS.get(m[1].lower())) and (result := _end_of_month(int(m[2]), month)):
            return result
    return None


def _add(found: list[tuple[int, date]], pos: int, year: int, month: int, day: int) -> None:
    if not 1900 <= year <= 2100:
        return
    try:
        found.append((pos, date(year, month, day)))
    except ValueError:
        pass


def _end_of_month(year: int, month: int) -> date | None:
    if not (1900 <= year <= 2100 and 1 <= month <= 12):
        return None
    return date(year, month, calendar.monthrange(year, month)[1])
