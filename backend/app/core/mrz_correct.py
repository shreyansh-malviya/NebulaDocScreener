"""MRZ OCR post-correction pipeline (pure Python, no dependencies).

Implements the staged correction idea for the MRZ, which is an IDEAL target because it is
(a) fixed-format, (b) OCR-B font, and (c) self-verifying via ICAO check digits:

  Stage 1  POSITIONAL coercion  — each MRZ position has a known type (letters vs digits),
           so a digit misread as a letter (or vice-versa) is fixed by position.
  Stage 2  CHECK-DIGIT-GUIDED repair — for a field whose check digit fails, try visually
           CONFUSABLE substitutions until the check digit passes (locates + fixes the error).

IMPORTANT (anti-masking): corrections are restricted to VISUALLY CONFUSABLE characters and
every change is recorded. A deliberate tamper (an arbitrary value change) is not an OCR
confusion, so it cannot be "corrected" away — and the composite check digit is a backstop.
This corrector improves reading of NOISY SCANS; it does not decide authenticity. Run it on
the image-OCR path, never to override the security cross-checks (MRZ↔VIZ↔chip + pixel forensics).
"""
from __future__ import annotations

from .mrz import _clean_line, check_digit, detect_format, parse_mrz

# Visual-confusion map (bidirectional-ish); values are chars that look like the key.
CONFUSABLE: dict[str, str] = {
    "0": "ODQ8", "O": "0Q", "D": "0O", "Q": "0O",
    "1": "IL7", "I": "1L", "L": "1I",
    "2": "Z7", "Z": "2",
    "5": "S6", "S": "5",
    "6": "G58", "G": "6",
    "8": "B06", "B": "8",
    "4": "A9", "A": "4",
    "7": "1T2", "T": "7",
    "9": "04", "3": "8",
}
LETTER_TO_DIGIT = {"O": "0", "Q": "0", "D": "0", "I": "1", "L": "1", "Z": "2",
                   "S": "5", "B": "8", "G": "6", "A": "4", "T": "7"}
DIGIT_TO_LETTER = {"0": "O", "1": "I", "2": "Z", "5": "S", "8": "B", "6": "G", "4": "A", "7": "T"}

# TD3 positional templates (0-indexed, length 44): N=numeric, A=alpha, X=alnum, S=sex.
_TD3_L1 = "AXAAA" + "X" * 39
_TD3_L2 = ("X" * 9) + "N" + ("A" * 3) + ("N" * 6) + "N" + "S" + ("N" * 6) + "N" + ("X" * 14) + "N" + "N"


def _positional(line: str, tmpl: str) -> tuple[str, list]:
    out = list(line)
    changes = []
    for i, ch in enumerate(line):
        t = tmpl[i] if i < len(tmpl) else "X"
        c = ch
        if t == "N" and ch != "<" and not ch.isdigit():
            c = LETTER_TO_DIGIT.get(ch.upper(), ch)
        elif t == "A" and ch.isdigit():
            c = DIGIT_TO_LETTER.get(ch, ch)
        if c != ch:
            out[i] = c
            changes.append({"pos": i, "from": ch, "to": c, "stage": "positional"})
    return "".join(out), changes


def _repair_field(field: str, printed_cd: str, numeric: bool) -> tuple[str, list, bool]:
    """If the field's check digit fails, try confusable substitutions to make it pass.

    A mod-10 check digit cannot UNIQUELY locate a single error, so we only auto-apply when
    exactly ONE confusable substitution satisfies it; multiple solutions → ambiguous (flag
    for review). In the image pipeline, per-character OCR confidence disambiguates these.
    Returns (field, changes, ambiguous).
    """
    if not printed_cd.isdigit():
        return field, [], False
    target = int(printed_cd)
    if check_digit(field) == target:
        return field, [], False
    solutions = []
    for i, ch in enumerate(field):
        for alt in CONFUSABLE.get(ch.upper(), ""):
            if numeric and not alt.isdigit():
                continue
            if check_digit(field[:i] + alt + field[i + 1:]) == target:
                solutions.append((i, ch, alt))
    if len(solutions) == 1:
        i, ch, alt = solutions[0]
        return field[:i] + alt + field[i + 1:], [{"pos": i, "from": ch, "to": alt, "stage": "check-digit"}], False
    return field, [], (len(solutions) > 1)


def _correct_td3(l1: str, l2: str) -> tuple[str, str, list]:
    changes: list = []
    l1, c1 = _positional(l1.ljust(44, "<")[:44], _TD3_L1)
    l2, c2 = _positional(l2.ljust(44, "<")[:44], _TD3_L2)
    changes += c1 + c2

    # check-digit-guided repair on each field (doc/opt are alnum; dob/expiry numeric)
    segments = [("doc_number", 0, 9, 9, False), ("dob", 13, 19, 19, True),
                ("expiry", 21, 27, 27, True), ("optional", 28, 42, 42, False)]
    l2l = list(l2)
    ambiguous: list = []
    for name, s, e, cd_pos, numeric in segments:
        fixed, ch, amb = _repair_field(l2[s:e], l2[cd_pos], numeric)
        if fixed != l2[s:e]:
            l2l[s:e] = list(fixed)
            for c in ch:
                c["pos"] += s
                c["field"] = name
            changes += ch
        if amb:
            ambiguous.append(name)
    return l1, "".join(l2l), changes, ambiguous


def correct_mrz(lines: list[str]) -> dict:
    """Correct OCR errors in MRZ lines. Returns corrected lines + the list of corrections
    + validity before/after (all check digits). Currently corrects TD3; others pass through."""
    cleaned = [_clean_line(l) for l in lines if l.strip()]
    fmt = detect_format(cleaned)
    before = parse_mrz(cleaned)

    if fmt == "TD3" and len(cleaned) >= 2:
        l1, l2, changes, ambiguous = _correct_td3(cleaned[0], cleaned[1])
        corrected = [l1, l2]
    else:
        corrected, changes, ambiguous = cleaned, [], []

    after = parse_mrz(corrected)
    return {
        "format": fmt,
        "corrected_lines": corrected,
        "corrections": changes,
        "num_corrections": len(changes),
        "ambiguous_fields": ambiguous,        # fields where the check digit had >1 confusable fix
        "valid_before": before["valid"],
        "valid_after": after["valid"],
    }
