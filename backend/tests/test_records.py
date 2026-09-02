"""Tests for the watchlist + multiple-identity (gallery) database checks."""
import asyncio

from app.core.fusion import fuse
from app.core.records import check_records
from app.models import Evidence
from app.storage.db import MemoryStore


def test_fusion_watchlist_gate():
    ev = Evidence()
    ev.records.watchlist_hit = True
    f = fuse(ev)
    assert f.band == "HIGH" and f.gate_fired == "WATCHLIST_HIT"


def test_fusion_identity_alert_floor():
    ev = Evidence()
    ev.m2_validation.checksums = {"doc_number": True, "dob": True, "expiry": True, "composite": True}
    ev.m2_validation.expiry_state = "VALID"
    ev.records.identity_alerts = ["same face seen under a different document number"]
    f = fuse(ev)
    assert f.band in ("MEDIUM", "HIGH")


def _ev(doc_number, emb):
    ev = Evidence()
    ev.m1_ocr.mrz.present = True
    ev.m1_ocr.mrz.fields = {"doc_number": doc_number}
    ev.m4_face.doc_embedding = emb
    return ev


def test_watchlist_and_identity_gallery():
    async def _run():
        store = MemoryStore()
        await store.watchlist_add({"value": "L898902C3", "type": "doc_number", "reason": "mock lost/stolen"})

        # 1) watchlisted document number → hit
        rc1 = await check_records(_ev("L898902C3", [1.0, 0.0, 0.0]), store)
        assert rc1.watchlist_hit is True

        # 2) SAME face, DIFFERENT document number → multiple-identity alert
        rc2 = await check_records(_ev("T7777777", [1.0, 0.0, 0.0]), store)
        assert any("multiple identities" in a for a in rc2.identity_alerts)

        # 3) SAME document number, DIFFERENT face → photo-substitution alert
        rc3 = await check_records(_ev("L898902C3", [0.0, 1.0, 0.0]), store)
        assert any("photo substitution" in a for a in rc3.identity_alerts)

    asyncio.run(_run())
