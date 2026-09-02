"""Module 5 — Chip PKI (ICAO eMRTD Passive/Active Authentication).

REAL cryptography via core.emrtd (ECDSA + X.509 CSCA→DSC). For the demo we synthesise a
chip from the passport data and verify it:
  genuine  → PA PASS + AA PASS → VERIFIED
  tampered → a data group edited after signing → PA FAIL (hash mismatch) → fusion HIGH gate
  cloned   → readable data intact but no AA private key → AA FAIL → fusion CHIP_CLONE gate
See Rough/research/04-orchestration-blockchain-arch.md §2.1.
"""
from __future__ import annotations

from ..core import emrtd
from ..core.types import ScreenInputs
from ..models import M5Chip


async def run(inputs: ScreenInputs) -> M5Chip:
    m5 = M5Chip()
    mode = (inputs.chip_mode or "none").lower()

    if mode == "none":
        m5.status = "ABSENT"
        m5.notes.append("No chip presented (typical at SSB open land borders — CV+biometric path is primary).")
        return m5

    # Synthesise the chip data groups from the presented passport.
    dg1 = ("\n".join(inputs.mrz_lines)).encode() if inputs.mrz_lines else b"NO-MRZ-PROVIDED"
    dg2 = inputs.live_face_bytes or b"NO-FACE-PLACEHOLDER"

    chip = emrtd.issue_chip(dg1, dg2, mode=mode)
    pa = emrtd.passive_authentication(chip)
    aa = emrtd.active_authentication(chip)
    m5.passive_auth = pa
    m5.active_auth = aa

    presented = "\n".join(inputs.mrz_lines) if inputs.mrz_lines else ""
    chip_dg1 = chip.data_groups["DG1"].decode(errors="replace")
    m5.chip_vs_printed = {"mrz_match": chip_dg1 == presented}

    if pa["result"] == "PASS" and aa["result"] == "PASS":
        m5.status = "VERIFIED"
    else:
        m5.status = "FAILED"
    m5.notes.append(
        f"Simulated eMRTD — Passive Auth={pa['result']}, Active Auth={aa['result']} (mode={mode}). "
        "Real ECDSA + X.509 CSCA→DSC; production uses ICAO PKD trust anchors."
    )
    return m5
