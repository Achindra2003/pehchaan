"""Name comparison for Indian names across documents, forms and OCR output."""

from __future__ import annotations

import re

from indic_namematch import NameMatcher

_matcher = NameMatcher()
APPROVE_AT = _matcher.bands.approve_at
REJECT_BELOW = _matcher.bands.reject_below


def tokens(name: str) -> list[str]:
    return [t.lower() for t in re.findall(r"[A-Za-z]+", name)]


_OCR_CONFUSIONS = (("rn", "m"), ("vv", "w"), ("l", "i"), ("1", "i"), ("0", "o"), ("5", "s"))


def _ocr_normalise(name: str) -> str:
    """Collapse characters OCR engines confuse ('Iyer' read as 'lyer'). Applied to both sides."""
    text = name.lower()
    for wrong, right in _OCR_CONFUSIONS:
        text = text.replace(wrong, right)
    return text


def name_score(a: str | None, b: str | None) -> float:
    if not a or not b:
        return 0.0
    score = _raw_score(a, b)
    if score < APPROVE_AT:
        score = max(score, _raw_score(_ocr_normalise(a), _ocr_normalise(b)))
    return score


def _raw_score(a: str, b: str) -> float:
    ta, tb = tokens(a), tokens(b)
    if not ta or not tb:
        return 0.0
    if "".join(ta) == "".join(tb):
        return 1.0
    # OCR engines sometimes glue tokens together ("AshaRao"); accept either token order.
    glued_a, glued_b = "".join(ta), "".join(tb)
    if len(ta) == 1 and glued_a in {"".join(tb), "".join(reversed(tb))}:
        return 0.97
    if len(tb) == 1 and glued_b in {"".join(ta), "".join(reversed(ta))}:
        return 0.97
    return float(_matcher.score(" ".join(ta), " ".join(tb)))
