"""Pre-flight self-test — REAL verification of the deterministic core.

Runs known-answer checks on the check-digit math, MRZ parse (valid + tampered), the
fusion truth-table, ledger integrity + tamper detection, and a storage roundtrip.
Exposed at GET /api/selftest and used as the boot readiness board (see build-plan §6).
"""
from __future__ import annotations

from ..core import mrz as mrzlib
from ..core.fusion import fuse
from ..core.ledger import Ledger
from ..models import Evidence
from ..storage.db import MemoryStore


async def run_selftest() -> dict:
    results: list[dict] = []

    def add(name: str, ok: bool, detail: str = "") -> None:
        results.append({"check": name, "ok": bool(ok), "detail": detail})

    # 1) canonical check digit
    cd = mrzlib.check_digit("L898902C3")
    add("check_digit('L898902C3') == 6", cd == 6, f"got {cd}")

    # 2) canonical valid TD3 parses & validates
    l1 = "P<UTOERIKSSON<<ANNA<MARIA<<<<<<<<<<<<<<<<<<<"
    l2 = "L898902C36UTO7408122F1204159ZE184226B<<<<<10"
    p = mrzlib.parse_mrz([l1, l2])
    add("canonical TD3 valid", p["valid"], f"checks={p['checks']}")

    # 3) tampered TD3 (DOB digit flipped) is detected
    l2t = l2[:13] + "5" + l2[14:]  # 740812 -> 750812, check digit not updated
    pt = mrzlib.parse_mrz([l1, l2t])
    add("tampered DOB detected",
        pt["checks"].get("dob") is False or pt["checks"].get("composite") is False,
        f"checks={pt['checks']}")

    # 4) fusion fires a hard gate on a checksum failure
    ev = Evidence()
    ev.m2_validation.checksums = {"dob": False, "composite": True}
    ev.m2_validation.expiry_state = "VALID"
    f1 = fuse(ev)
    add("fusion HIGH gate on checksum fail",
        f1.band == "HIGH" and f1.gate_fired == "MRZ_CHECKSUM_FAIL",
        f"band={f1.band} gate={f1.gate_fired}")

    # 5) fusion clears a clean document to LOW
    ev2 = Evidence()
    ev2.m2_validation.checksums = {"doc_number": True, "dob": True, "expiry": True, "composite": True}
    ev2.m2_validation.expiry_state = "VALID"
    f2 = fuse(ev2)
    add("fusion clean -> LOW", f2.band == "LOW", f"band={f2.band}")

    # 6) ledger: intact after appends, then detects a tamper at the exact seq
    store = MemoryStore()
    led = Ledger(store, "selftest-secret")
    e = Evidence(); e.fusion = f2
    await led.append_screening(e)
    e2 = Evidence(); e2.fusion = f1
    await led.append_screening(e2)
    v = await led.verify()
    add("ledger intact after 2 appends", v["intact"], str(v))
    v2 = await led.demo_tamper(0, band="LOW")
    add("ledger detects tamper at seq 0", (not v2["intact"]) and (0 in v2["broken_seqs"]), str(v2))

    # 7) storage blob roundtrip
    ref, digest = await store.put_blob(b"nebula")
    blob = await store.get_blob(ref)
    add("storage blob roundtrip", blob == b"nebula", f"digest={digest[:12]}…")

    passed = sum(1 for r in results if r["ok"])
    return {"passed": passed, "total": len(results), "all_ok": passed == len(results), "checks": results}
