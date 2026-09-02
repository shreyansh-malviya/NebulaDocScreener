"""Cross-document identity matching (name + DOB).

Policy basis (Rough/research/10-regulatory-matching-rules.md §Q2): there is NO published
national name-matching algorithm, but cross-document consistency IS required in practice for
**passport ↔ visa** (a visa is issued against a specific passport) and is the mechanism behind
the PS's "identity impersonation / multiple identities" objectives. Thresholds here are OUR
documented policy, not a statutory figure. Output is ADVISORY — the officer decides.

Pure Python (difflib), no dependencies. Names are compared order-independently with initials
and spelling-variant tolerance; DOB is compared exactly (both normalised to digits).
"""
from __future__ import annotations

import difflib
import re
from typing import Optional

# OUR policy thresholds for the name-similarity bands (0..1). Calibrate on real pairs.
NAME_ACCEPT = 0.90
NAME_REVIEW = 0.70


def _name_tokens(s: str) -> list[str]:
    return re.sub(r"[^A-Z ]", " ", (s or "").upper()).split()


def _alnum(s: str) -> str:
    return re.sub(r"[^A-Z0-9]", "", (s or "").upper())


def _dob_digits(s: str) -> str:
    d = re.sub(r"\D", "", s or "")
    return d[-6:] if len(d) >= 6 else d      # normalise to YYMMDD tail


def name_similarity(a: str, b: str) -> float:
    ta, tb = _name_tokens(a), _name_tokens(b)
    if not ta or not tb:
        return 0.0
    # order-independent string ratio
    base = difflib.SequenceMatcher(None, " ".join(sorted(ta)), " ".join(sorted(tb))).ratio()

    def covers(x: str, ys: list[str]) -> float:
        best = 0.0
        for y in ys:
            if x == y:
                return 1.0
            if (len(x) == 1 and y[:1] == x) or (len(y) == 1 and x[:1] == y):
                best = max(best, 0.9)                      # initial ↔ full name
            best = max(best, difflib.SequenceMatcher(None, x, y).ratio())
        return best

    cov_a = sum(covers(x, tb) for x in ta) / len(ta)
    cov_b = sum(covers(y, ta) for y in tb) / len(tb)
    return round(max(base, (cov_a + cov_b) / 2), 4)


def match_names(a: str, b: str) -> tuple[float, str]:
    s = name_similarity(a, b)
    band = "ACCEPT" if s >= NAME_ACCEPT else ("REVIEW" if s >= NAME_REVIEW else "MISMATCH")
    return s, band


def match_dob(a: str, b: str) -> bool:
    da, db = _dob_digits(a), _dob_digits(b)
    return bool(da) and da == db


def cross_match(extracted: dict, reference: Optional[dict]) -> dict:
    """Compare an extracted document's identity against a reference document's identity."""
    out: dict = {"checked": False}
    if not reference or not any((reference or {}).values()):
        return out
    out["checked"] = True
    reasons: list[str] = []
    issues = 0

    if reference.get("name") and extracted.get("name"):
        score, band = match_names(reference["name"], extracted["name"])
        out["name"] = {"score": score, "band": band}
        if band == "MISMATCH":
            reasons.append(f"Name MISMATCH across documents (similarity {score}).")
            issues += 1
        elif band == "REVIEW":
            reasons.append(f"Name differs across documents (similarity {score}) — manual review.")

    if reference.get("dob") and extracted.get("dob"):
        ok = match_dob(reference["dob"], extracted["dob"])
        out["dob"] = {"match": ok}
        if not ok:
            reasons.append("Date-of-birth MISMATCH across documents.")
            issues += 1

    if reference.get("doc_number") and extracted.get("doc_number"):
        out["doc_number"] = {"match": _alnum(reference["doc_number"]) == _alnum(extracted["doc_number"])}

    out["consistent"] = issues == 0
    out["reasons"] = reasons
    return out
