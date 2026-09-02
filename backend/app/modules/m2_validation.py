"""Module 2 — Document validation (PURE RULES, no ML).

Deterministic, explainable, offline: check-digit verdicts, date logic, country-code
sanity, and the MRZ<->VIZ cross-check (the strongest cheap tamper signal). Failures here
become hard gates in the fusion engine.
"""
from __future__ import annotations

import re
from datetime import date

from ..models import M1OCR, M2Validation

# Minimal ICAO-specific codes that are valid but not ISO-3166 alpha-3 (avoid false flags).
_ICAO_EXTRA = {"UNO", "UNA", "UNK", "XXA", "XXB", "XXC", "XXX", "GBD", "GBN", "GBO", "GBP", "GBS", "D"}


def _parse_yymmdd(s: str, is_expiry: bool) -> date | None:
    if not (len(s) == 6 and s.isdigit()):
        return None
    yy, mm, dd = int(s[0:2]), int(s[2:4]), int(s[4:6])
    if is_expiry:
        year = 2000 + yy                     # travel-doc expiries are this century
    else:
        year = 2000 + yy
        if year > date.today().year:         # a "future" DOB must be last century
            year -= 100
    try:
        return date(year, mm, dd)
    except ValueError:
        return None


def _norm(v: str) -> str:
    return re.sub(r"[^A-Z0-9]", "", str(v).upper())


async def run(m1: M1OCR) -> M2Validation:
    m2 = M2Validation()

    if not m1.mrz.present:
        m2.status = "SKIPPED"
        m2.reasons.append("No MRZ available to validate.")
        return m2

    fields = m1.mrz.fields
    raw = m1.mrz.raw_check_digits
    comp = m1.mrz.computed_check_digits

    # ---- check digits (raw printed vs computed) ----
    checks: dict[str, bool | None] = {}
    for k in comp:
        if k == "optional":
            opt = str(fields.get("optional", "") or "")
            checks[k] = True if (opt.strip() == "" and raw.get(k) in ("<", "0")) else (raw.get(k) == comp.get(k))
        else:
            checks[k] = raw.get(k) == comp.get(k)
    m2.checksums = checks
    for k, ok in checks.items():
        if ok is False:
            m2.reasons.append(f"Check-digit MISMATCH on {k} (MRZ printed {raw.get(k)!r} vs computed {comp.get(k)!r}).")

    # ---- dates ----
    dob = _parse_yymmdd(str(fields.get("dob", "")), is_expiry=False)
    expiry = _parse_yymmdd(str(fields.get("expiry", "")), is_expiry=True)
    today = date.today()
    if expiry is None:
        m2.expiry_state = "UNKNOWN"
    elif expiry >= today:
        m2.expiry_state = "VALID"
    else:
        m2.expiry_state = "EXPIRED"
        m2.reasons.append(f"Document EXPIRED on {expiry.isoformat()}.")

    if dob and expiry:
        age = today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))
        m2.date_logic_ok = (dob < expiry) and (0 <= age < 120)
        if not m2.date_logic_ok:
            m2.reasons.append(f"Date logic implausible (DOB {dob.isoformat()}, expiry {expiry.isoformat()}, age {age}).")
    else:
        m2.date_logic_ok = None

    # ---- country / nationality code (lightweight; full ISO-3166 via pycountry later) ----
    nat = str(fields.get("nationality") or fields.get("issuing_country") or "")
    if nat:
        valid = bool(re.fullmatch(r"[A-Z]{3}", nat)) or nat in _ICAO_EXTRA
        m2.country_code_valid = valid
        if not valid:
            m2.reasons.append(f"Country/nationality code looks invalid: {nat!r}.")

    # ---- MRZ <-> VIZ cross-check (printed vs machine-readable) ----
    if m1.viz:
        match: dict[str, bool | None] = {}
        for key, printed in m1.viz.items():
            if printed in (None, ""):
                continue
            mrz_val = fields.get(key)
            if mrz_val is None:
                match[key] = None
                continue
            match[key] = _norm(printed) == _norm(mrz_val)
            if match[key] is False:
                m2.reasons.append(f"MRZ<->printed MISMATCH on {key} (printed {printed!r} vs MRZ {mrz_val!r}).")
        m2.viz_mrz_match = match

    m2.hard_fail = any(v is False for v in checks.values())
    m2.status = "OK"
    if not m2.reasons:
        m2.reasons.append("All MRZ check digits valid; dates and codes consistent.")
    return m2
