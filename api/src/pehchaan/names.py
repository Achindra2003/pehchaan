"""Name comparison for Indian names across documents, forms and OCR output."""

from __future__ import annotations

import re

from indic_namematch import NameMatcher

_matcher = NameMatcher()
APPROVE_AT = _matcher.bands.approve_at
REJECT_BELOW = _matcher.bands.reject_below


def tokens(name: str) -> list[str]:
    return [t.lower() for t in re.findall(r"[A-Za-z]+", name)]


def name_score(a: str | None, b: str | None) -> float:
    if not a or not b:
        return 0.0
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
