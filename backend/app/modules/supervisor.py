"""Supervisor — officer-facing narrative.

REAL template narrative now (deterministic, offline, always works). It reads ONLY the
structured Evidence — never raw document text/images — which is the prompt-injection
defence for the optional LLM version (Week 3). See 05-INTERNAL-DESIGN.md §5.
"""
from __future__ import annotations

from ..config import settings
from ..models import Evidence, Narrative

_GATE_TEXT = {
    "CHIP_PA_FAIL": "the passport chip failed Passive Authentication (cryptographic proof the data was altered)",
    "MRZ_CHECKSUM_FAIL": "one or more MRZ check digits do not match (the document is internally inconsistent)",
    "LIVENESS_SPOOF": "the live capture was flagged as a presentation attack (photo/screen replay)",
    "CHIP_CLONE": "the chip failed Active Authentication (possible clone)",
}


def narrate(ev: Evidence, cfg=settings) -> Narrative:
    f = ev.fusion
    parts: list[str] = [f"Risk {f.band}."]

    if f.gate_fired:
        parts.append(f"Reason: {_GATE_TEXT.get(f.gate_fired, f.gate_fired)}.")
    else:
        top = sorted([c for c in f.contributions if c.risk > 0], key=lambda c: c.risk, reverse=True)[:3]
        if top:
            parts.append("Main contributors: " + ", ".join(f"{c.signal} ({c.risk:.2f})" for c in top) + ".")
        if f.abstain:
            parts.append("Evidence is insufficient/low-quality to clear automatically — routed to manual review.")

    # deterministic validation detail (the reliable, always-present part)
    m2 = ev.m2_validation
    if m2.checksums:
        failed = [k for k, v in m2.checksums.items() if v is False]
        if failed:
            parts.append("Failed MRZ check digits: " + ", ".join(failed) + ".")
        else:
            parts.append("All MRZ check digits valid.")
    if m2.expiry_state == "EXPIRED":
        parts.append("Document is expired.")
    mismatched = [k for k, v in (m2.viz_mrz_match or {}).items() if v is False]
    if mismatched:
        parts.append("Printed vs MRZ mismatch on: " + ", ".join(mismatched) + ".")

    if ev.m3_tamper.tampered_fields:
        parts.append("Tamper localised over: " + ", ".join(ev.m3_tamper.tampered_fields) + ".")
    if ev.m4_face.match_zone:
        parts.append(f"Face match: {ev.m4_face.match_zone}.")

    parts.append(f"Recommended action: {f.recommended_action}")
    parts.append("The officer makes the final decision; this is decision support.")

    return Narrative(text=" ".join(parts), source="template", grounded=True)
