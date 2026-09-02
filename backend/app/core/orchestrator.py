"""Orchestrator — the deterministic DAG that runs the pipeline.

Runs M1 first (M2 depends on it), then fans M2..M5 out in parallel, each TIMEBOXED and
sandboxed so a slow/failing module degrades to `abstain` instead of crashing the screening.
Then: deterministic fusion → template narrative → persist → seal into the audit ledger.
No LLM in this control path (see 05-INTERNAL-DESIGN.md §2).
"""
from __future__ import annotations

import asyncio
import time
from datetime import datetime, timezone

from ..config import settings
from ..models import (Context, Evidence, LedgerRef, M1OCR, M2Validation,
                      M3Tamper, M4Face, M5Chip)
from ..modules import m1_ocr, m2_validation, m3_tamper, m4_face, m5_chip, supervisor
from .fusion import fuse
from .types import ScreenInputs


async def _safe(name, coro, cls, timeout, timings):
    """Run a module coroutine timeboxed; on timeout/error return a FAILED fragment."""
    start = time.perf_counter()
    try:
        frag = await asyncio.wait_for(coro, timeout)
        timings[name] = round(time.perf_counter() - start, 4)
        return frag
    except asyncio.TimeoutError:
        timings[name] = round(timeout, 4)
        f = cls(); f.status = "FAILED"
        f.notes.append(f"{name} timed out after {timeout}s → abstain.")
        return f
    except Exception as exc:  # never propagate — partial evidence still yields a verdict
        timings[name] = round(time.perf_counter() - start, 4)
        f = cls(); f.status = "FAILED"
        f.notes.append(f"{name} error: {type(exc).__name__}: {exc} → abstain.")
        return f


class Screener:
    def __init__(self, store, ledger):
        self.store = store
        self.ledger = ledger

    async def screen(self, inputs: ScreenInputs) -> Evidence:
        ev = Evidence(config_version=settings.CONFIG_VERSION, station_id=settings.STATION_ID)
        ev.context = Context(doc_type=inputs.doc_type, chip_present=inputs.chip_present)

        # store original bytes (kept untouched — the ledger anchors on their SHA-256)
        if inputs.document_bytes:
            ref, digest = await self.store.put_blob(
                inputs.document_bytes, {"kind": "document", "filename": inputs.document_filename})
            ev.context.doc_image_ref, ev.context.doc_image_sha256 = ref, digest
        if inputs.live_face_bytes:
            ref, _ = await self.store.put_blob(inputs.live_face_bytes, {"kind": "live_face"})
            ev.context.live_face_ref = ref

        timings: dict[str, float] = {}
        tb = settings.TIMEBOX

        # M1 first (M2 consumes its MRZ)
        ev.m1_ocr = await _safe("m1_ocr", m1_ocr.run(inputs), M1OCR, tb["m1_ocr"], timings)

        # M2..M5 in parallel
        m2, m3, m4, m5 = await asyncio.gather(
            _safe("m2_validation", m2_validation.run(ev.m1_ocr), M2Validation, tb["m2_validation"], timings),
            _safe("m3_tamper", m3_tamper.run(inputs), M3Tamper, tb["m3_tamper"], timings),
            _safe("m4_face", m4_face.run(inputs), M4Face, tb["m4_face"], timings),
            _safe("m5_chip", m5_chip.run(inputs), M5Chip, tb["m5_chip"], timings),
        )
        ev.m2_validation, ev.m3_tamper, ev.m4_face, ev.m5_chip = m2, m3, m4, m5
        ev.module_timings = timings

        # deterministic verdict, then narrative
        ev.fusion = fuse(ev)
        ev.narrative = supervisor.narrate(ev)

        # persist, then seal into the tamper-evident ledger
        await self.store.save_session(ev.model_dump(mode="json"))
        rec = await self.ledger.append_screening(ev)
        ev.ledger = LedgerRef(seq=rec["seq"], prev_hash=rec["prev_hash"],
                              record_hash=rec["record_hash"], signature=rec["signature"])
        await self.store.save_session(ev.model_dump(mode="json"))  # re-save with ledger ref
        return ev

    async def decide(self, session_id: str, action: str) -> Evidence | None:
        doc = await self.store.get_session(session_id)
        if not doc:
            return None
        ev = Evidence.model_validate(doc)
        ev.decision.officer_action = action
        ev.decision.at = datetime.now(timezone.utc)
        await self.ledger.append_decision(ev, action)   # a NEW linked record, original untouched
        await self.store.save_session(ev.model_dump(mode="json"))
        return ev
