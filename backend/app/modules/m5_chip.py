"""Module 5 — Chip PKI (ICAO eMRTD Passive/Active Authentication).  [STUB — Week 2]

Clearly-labelled STUB: status ABSENT (or STUB if a chip was flagged present) with an
empty passive_auth (so it never fires the crypto gate). The real Passive Authentication
(simulated CSCA->DSC + EF.SOD, and the flip-a-byte demo) lands Week 2.
"""
from __future__ import annotations

from ..core.types import ScreenInputs
from ..models import M5Chip


async def run(inputs: ScreenInputs) -> M5Chip:
    m5 = M5Chip()
    if inputs.chip_present:
        m5.status = "STUB"
        m5.notes.append("Chip Passive-Auth pending (Week 2): simulated CSCA->DSC + EF.SOD + flip-a-byte.")
    else:
        m5.status = "ABSENT"
        m5.notes.append("No chip presented (typical at SSB open land borders — CV+biometric path is primary).")
    return m5
