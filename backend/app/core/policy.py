"""Document-acceptance policy — encodes the SSB/BoI border-crossing criteria.

Grounded in Rough/research/07-border-crossing-rules.md + 10-regulatory-matching-rules.md:
which document types are valid to cross which border, for whom. This is a DATA-DRIVEN
policy table (easy to update as rules change) with effective-date awareness in mind.

Honest scope: acceptance is ADVISORY input to the risk score — it never auto-rejects a
traveller (the officer decides, per Immigration & Foreigners Act 2025 s.3).
"""
from __future__ import annotations

from typing import Optional

# Accepted TRAVEL documents by (traveller-nationality ISO3, border being crossed).
ACCEPTED_TRAVEL_DOCS: dict[tuple[str, str], set[str]] = {
    ("IND", "NEPAL"): {"PASSPORT", "VOTER_ID"},
    ("IND", "BHUTAN"): {"PASSPORT", "VOTER_ID"},
    ("NPL", "INDIA"): {"PASSPORT", "CITIZENSHIP_CERT", "VOTER_ID"},
    ("BTN", "INDIA"): {"PASSPORT", "VOTER_ID"},
}

# Never valid as a travel document to cross these borders (the hard-reject list).
HARD_REJECT: set[str] = {"AADHAAR", "PAN", "DRIVING_LICENSE", "RATION_CARD"}

# Narrow land-crossing age exceptions (Nepal): age proof accepted for these bands.
_LAND_AGE_EXCEPTION_BANDS = {"UNDER_18", "65_PLUS"}


def check_acceptance(doc_type: Optional[str], nationality: Optional[str], border: Optional[str],
                     mode: Optional[str] = None, age_band: Optional[str] = None) -> dict:
    """Return {accepted: True|False|None, reason: str}. None = context incomplete → not evaluated."""
    doc = (doc_type or "").upper()
    nat = (nationality or "").upper()
    brd = (border or "").upper()
    md = (mode or "").upper()
    age = (age_band or "").upper()

    if not doc or not nat or not brd or brd == "OTHER":
        return {"accepted": None,
                "reason": "Crossing context incomplete (need document type + nationality + border); acceptance not evaluated."}

    if doc in HARD_REJECT:
        # A very narrow tolerance exists for age proof on Nepal LAND crossings — surface it, still not a travel doc.
        if brd == "NEPAL" and md == "LAND" and age in _LAND_AGE_EXCEPTION_BANDS:
            return {"accepted": False,
                    "reason": f"{doc} is NOT a travel document; only tolerated as age proof for {age} on Nepal land crossings. Verify manually."}
        return {"accepted": False,
                "reason": f"{doc} is NOT an accepted travel document for border crossing (SSB/BoI rules — use Passport or Voter ID/EPIC)."}

    # Third-country nationals: passport + visa, authorised ICPs only.
    if nat not in {"IND", "NPL", "BTN"}:
        ok = doc == "PASSPORT"
        return {"accepted": ok,
                "reason": ("Passport accepted (third-country national — visa verified separately)."
                           if ok else "Third-country national: a valid passport + visa is required.")}

    allowed = ACCEPTED_TRAVEL_DOCS.get((nat, brd))
    if allowed is None:
        return {"accepted": None, "reason": f"No acceptance rule configured for {nat} → {brd}."}
    ok = doc in allowed
    return {"accepted": ok,
            "reason": (f"{doc} is accepted for {nat} → {brd}." if ok
                       else f"{doc} is not in the accepted set {sorted(allowed)} for {nat} → {brd}.")}
