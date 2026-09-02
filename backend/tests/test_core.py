"""Real unit tests for the deterministic core (run: cd backend && python -m pytest)."""
import asyncio

from app.core import mrz
from app.core.fusion import fuse
from app.core.ledger import Ledger
from app.models import Evidence
from app.storage.db import MemoryStore

VALID_L1 = "P<UTOERIKSSON<<ANNA<MARIA<<<<<<<<<<<<<<<<<<<"
VALID_L2 = "L898902C36UTO7408122F1204159ZE184226B<<<<<10"


def test_check_digit_canonical():
    assert mrz.check_digit("L898902C3") == 6      # ICAO Doc 9303 canonical example
    assert mrz.check_digit("740812") == 2
    assert mrz.check_digit("120415") == 9


def test_parse_valid_td3():
    p = mrz.parse_mrz([VALID_L1, VALID_L2])
    assert p["format"] == "TD3"
    assert p["valid"] is True
    assert all(v for v in p["checks"].values() if v is not None)


def test_parse_tampered_td3_detected():
    l2t = VALID_L2[:13] + "5" + VALID_L2[14:]     # 740812 -> 750812, check digit stale
    p = mrz.parse_mrz([VALID_L1, l2t])
    assert p["valid"] is False
    assert (p["checks"]["dob"] is False) or (p["checks"]["composite"] is False)


def test_build_td3_roundtrip():
    l1, l2 = mrz.build_td3("IND", "SHARMA", "ROHIT", "J8369854", "IND", "900101", "M", "320101")
    p = mrz.parse_mrz([l1, l2])
    assert p["valid"] is True
    assert p["fields"]["doc_number"] == "J8369854"
    assert p["fields"]["dob"] == "900101"


def test_fusion_gate_on_checksum_fail():
    ev = Evidence()
    ev.m2_validation.checksums = {"dob": False, "composite": True}
    ev.m2_validation.expiry_state = "VALID"
    f = fuse(ev)
    assert f.band == "HIGH" and f.gate_fired == "MRZ_CHECKSUM_FAIL"


def test_fusion_clean_low():
    ev = Evidence()
    ev.m2_validation.checksums = {"doc_number": True, "dob": True, "expiry": True, "composite": True}
    ev.m2_validation.expiry_state = "VALID"
    f = fuse(ev)
    assert f.band == "LOW" and f.gate_fired is None and f.abstain is False


def test_fusion_expired_floor():
    ev = Evidence()
    ev.m2_validation.checksums = {"doc_number": True, "dob": True, "expiry": True, "composite": True}
    ev.m2_validation.expiry_state = "EXPIRED"
    f = fuse(ev)
    assert f.band in ("MEDIUM", "HIGH")


def test_fusion_face_reject_raises_risk():
    ev = Evidence()
    ev.m2_validation.checksums = {"doc_number": True, "dob": True, "expiry": True, "composite": True}
    ev.m2_validation.expiry_state = "VALID"
    ev.m4_face.similarity = 0.05
    ev.m4_face.threshold = 0.45
    ev.m4_face.match_zone = "REJECT"
    f = fuse(ev)
    assert f.band in ("MEDIUM", "HIGH")


def test_ledger_integrity_and_tamper():
    async def _run():
        store = MemoryStore()
        led = Ledger(store, "test-key")
        await led.append_screening(Evidence())
        await led.append_screening(Evidence())
        v = await led.verify()
        assert v["intact"] is True and v["count"] == 2
        v2 = await led.demo_tamper(0, band="LOW")
        assert v2["intact"] is False and 0 in v2["broken_seqs"]

    asyncio.run(_run())
