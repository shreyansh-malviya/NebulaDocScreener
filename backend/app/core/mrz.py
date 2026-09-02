"""ICAO Doc 9303 MRZ parsing + check-digit validation.

Pure Python, ZERO dependencies. This is REAL, deterministic, offline logic — the
trustworthy backbone of Modules 1 & 2. Because the MRZ carries self-verifying check
digits, an altered passport number / DOB / expiry can be detected from the image alone,
with NO database (see Rough/research/01-ocr-mrz-validation.md §2).

Supports TD3 (passport, 2x44), TD1 (ID card, 3x30), TD2 (2x36).
"""
from __future__ import annotations

from typing import Optional

_WEIGHTS = (7, 3, 1)


def char_value(ch: str) -> int:
    """ICAO value map: '0'-'9' -> 0-9, 'A'-'Z' -> 10-35, '<' (filler) -> 0."""
    if ch == "<":
        return 0
    if ch.isdigit():
        return int(ch)
    ch = ch.upper()
    if "A" <= ch <= "Z":
        return ord(ch) - ord("A") + 10
    return 0  # defensive: unexpected char treated as filler


def check_digit(data: str) -> int:
    """ICAO 7-3-1 weighted checksum, mod 10. e.g. check_digit('L898902C3') == 6."""
    total = 0
    for i, ch in enumerate(data):
        total += char_value(ch) * _WEIGHTS[i % 3]
    return total % 10


def _clean_line(line: str) -> str:
    # MRZ uses only A-Z, 0-9, '<'. Uppercase and drop spaces (OCR often inserts them).
    return "".join(line.upper().split())


def _optional_ok(field: str, raw_cd: str, computed_cd: str) -> Optional[bool]:
    """Optional-data check digit: when the optional field is empty (all filler),
    the printed check digit is legitimately '<' or '0'."""
    if field.strip("<") == "":
        if raw_cd in ("<", "0"):
            return True
    return raw_cd == computed_cd


def detect_format(lines: list[str]) -> Optional[str]:
    cleaned = [_clean_line(l) for l in lines if l.strip()]
    n = len(cleaned)
    if n == 2 and all(len(l) == 44 for l in cleaned):
        return "TD3"
    if n == 2 and all(len(l) == 36 for l in cleaned):
        return "TD2"
    if n == 3 and all(len(l) == 30 for l in cleaned):
        return "TD1"
    # tolerant fallbacks by line count (OCR may drop/add a char)
    if n == 3:
        return "TD1"
    if n == 2 and cleaned and len(cleaned[0]) >= 40:
        return "TD3"
    if n == 2:
        return "TD2"
    return None


def _result(fmt, fields, raw, computed, checks, errors) -> dict:
    valid = all(v for v in checks.values() if v is not None) and not errors
    return {
        "format": fmt,
        "valid": valid,
        "fields": fields,
        "raw_check_digits": raw,
        "computed_check_digits": computed,
        "checks": checks,
        "errors": errors,
    }


def _parse_td3(l1: str, l2: str) -> dict:
    errors: list[str] = []
    if len(l1) != 44 or len(l2) != 44:
        errors.append(f"TD3 expects 2x44 chars, got {len(l1)}/{len(l2)}")
    l1 = l1.ljust(44, "<")[:44]
    l2 = l2.ljust(44, "<")[:44]

    names = l1[5:44]
    surname, _, given = names.partition("<<")
    fields = {
        "type": l1[0:2].replace("<", ""),
        "issuing_country": l1[2:5],
        "surname": surname.replace("<", " ").strip(),
        "given_names": given.replace("<", " ").strip(),
        "doc_number": l2[0:9].replace("<", ""),
        "nationality": l2[10:13],
        "dob": l2[13:19],
        "sex": l2[20],
        "expiry": l2[21:27],
        "optional": l2[28:42].replace("<", ""),
    }
    raw = {
        "doc_number": l2[9], "dob": l2[19], "expiry": l2[27],
        "optional": l2[42], "composite": l2[43],
    }
    composite_str = l2[0:10] + l2[13:20] + l2[21:43]
    computed = {
        "doc_number": str(check_digit(l2[0:9])),
        "dob": str(check_digit(l2[13:19])),
        "expiry": str(check_digit(l2[21:27])),
        "optional": str(check_digit(l2[28:42])),
        "composite": str(check_digit(composite_str)),
    }
    checks = {
        "doc_number": raw["doc_number"] == computed["doc_number"],
        "dob": raw["dob"] == computed["dob"],
        "expiry": raw["expiry"] == computed["expiry"],
        "optional": _optional_ok(l2[28:42], raw["optional"], computed["optional"]),
        "composite": raw["composite"] == computed["composite"],
    }
    return _result("TD3", fields, raw, computed, checks, errors)


def _parse_td2(l1: str, l2: str) -> dict:
    errors: list[str] = []
    if len(l1) != 36 or len(l2) != 36:
        errors.append(f"TD2 expects 2x36 chars, got {len(l1)}/{len(l2)}")
    l1 = l1.ljust(36, "<")[:36]
    l2 = l2.ljust(36, "<")[:36]

    names = l1[5:36]
    surname, _, given = names.partition("<<")
    fields = {
        "type": l1[0:2].replace("<", ""),
        "issuing_country": l1[2:5],
        "surname": surname.replace("<", " ").strip(),
        "given_names": given.replace("<", " ").strip(),
        "doc_number": l2[0:9].replace("<", ""),
        "nationality": l2[10:13],
        "dob": l2[13:19],
        "sex": l2[20],
        "expiry": l2[21:27],
        "optional": l2[28:35].replace("<", ""),
    }
    raw = {"doc_number": l2[9], "dob": l2[19], "expiry": l2[27], "composite": l2[35]}
    composite_str = l2[0:10] + l2[13:20] + l2[21:35]
    computed = {
        "doc_number": str(check_digit(l2[0:9])),
        "dob": str(check_digit(l2[13:19])),
        "expiry": str(check_digit(l2[21:27])),
        "composite": str(check_digit(composite_str)),
    }
    checks = {
        "doc_number": raw["doc_number"] == computed["doc_number"],
        "dob": raw["dob"] == computed["dob"],
        "expiry": raw["expiry"] == computed["expiry"],
        "composite": raw["composite"] == computed["composite"],
    }
    return _result("TD2", fields, raw, computed, checks, errors)


def _parse_td1(l1: str, l2: str, l3: str) -> dict:
    errors: list[str] = []
    if not (len(l1) == len(l2) == len(l3) == 30):
        errors.append(f"TD1 expects 3x30 chars, got {len(l1)}/{len(l2)}/{len(l3)}")
    l1 = l1.ljust(30, "<")[:30]
    l2 = l2.ljust(30, "<")[:30]
    l3 = l3.ljust(30, "<")[:30]

    surname, _, given = l3.partition("<<")
    fields = {
        "type": l1[0:2].replace("<", ""),
        "issuing_country": l1[2:5],
        "doc_number": l1[5:14].replace("<", ""),
        "optional_1": l1[15:30].replace("<", ""),
        "dob": l2[0:6],
        "sex": l2[7],
        "expiry": l2[8:14],
        "nationality": l2[15:18],
        "optional_2": l2[18:29].replace("<", ""),
        "surname": surname.replace("<", " ").strip(),
        "given_names": given.replace("<", " ").strip(),
    }
    raw = {"doc_number": l1[14], "dob": l2[6], "expiry": l2[14], "composite": l2[29]}
    composite_str = l1[5:30] + l2[0:7] + l2[8:15] + l2[18:29]
    computed = {
        "doc_number": str(check_digit(l1[5:14])),
        "dob": str(check_digit(l2[0:6])),
        "expiry": str(check_digit(l2[8:14])),
        "composite": str(check_digit(composite_str)),
    }
    checks = {
        "doc_number": raw["doc_number"] == computed["doc_number"],
        "dob": raw["dob"] == computed["dob"],
        "expiry": raw["expiry"] == computed["expiry"],
        "composite": raw["composite"] == computed["composite"],
    }
    return _result("TD1", fields, raw, computed, checks, errors)


def parse_mrz(lines: list[str]) -> dict:
    """Auto-detect format and parse+validate. Returns a dict (see _result).
    On unrecognised input returns {'format': None, 'valid': False, 'errors': [...]}."""
    cleaned = [_clean_line(l) for l in lines if l.strip()]
    fmt = detect_format(cleaned)
    if fmt == "TD3":
        return _parse_td3(cleaned[0], cleaned[1])
    if fmt == "TD2":
        return _parse_td2(cleaned[0], cleaned[1])
    if fmt == "TD1" and len(cleaned) >= 3:
        return _parse_td1(cleaned[0], cleaned[1], cleaned[2])
    return _result(fmt, {}, {}, {}, {}, [f"Unrecognised MRZ ({len(cleaned)} lines)"])


# --------------------------------------------------------------------------------------
# MRZ GENERATOR — build a VALID TD3 (correct check digits). Used to create legal synthetic
# test passports (no real documents needed — privacy/DPDP compliant). See build-plan §5.
# --------------------------------------------------------------------------------------
def build_td3(issuing: str, surname: str, given: str, doc_number: str, nationality: str,
              dob: str, sex: str, expiry: str, optional: str = "") -> tuple[str, str]:
    """Assemble a valid TD3 (passport) MRZ with correct ICAO check digits.
    dob/expiry are YYMMDD strings."""
    name = surname.upper().replace(" ", "<") + "<<" + given.upper().replace(" ", "<")
    l1 = ("P<" + issuing.upper() + name).ljust(44, "<")[:44]

    dn = doc_number.upper().ljust(9, "<")[:9]
    opt = optional.upper().ljust(14, "<")[:14]
    cd_dn, cd_dob, cd_exp, cd_opt = (str(check_digit(dn)), str(check_digit(dob)),
                                     str(check_digit(expiry)), str(check_digit(opt)))
    l2_wo = dn + cd_dn + nationality.upper() + dob + cd_dob + sex.upper() + expiry + cd_exp + opt + cd_opt
    composite_str = l2_wo[0:10] + l2_wo[13:20] + l2_wo[21:43]
    l2 = (l2_wo + str(check_digit(composite_str))).ljust(44, "<")[:44]
    return l1, l2


def sample_passport(tampered: bool = False) -> dict:
    """A legal synthetic Indian passport for demos.
    tampered=True flips a DOB digit in the MRZ WITHOUT fixing its check digit →
    the validator catches it (dob + composite check-digit failure)."""
    l1, l2 = build_td3("IND", "SHARMA", "ROHIT", "J8369854", "IND",
                       dob="900101", sex="M", expiry="320101")
    printed = {"dob": "900101", "doc_number": "J8369854", "expiry": "320101"}
    if tampered:
        # change 900101 -> 800101 in the MRZ (index 13) but leave the check digits alone
        l2 = l2[:13] + "8" + l2[14:]
    return {"line1": l1, "line2": l2, "line3": "", "doc_type": "PASSPORT", "printed": printed,
            "tampered": tampered}
