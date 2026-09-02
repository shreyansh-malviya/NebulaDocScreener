"""FastAPI application — the screening station API + minimal officer console.

Endpoints:
  GET  /                      minimal no-CSS console (static/index.html)
  GET  /api/health            backend status + storage backend in use
  GET  /api/selftest          run the deterministic-core self-test (readiness board)
  GET  /api/sample            a legal synthetic passport MRZ (valid or tampered)
  POST /api/screen            run a screening (paste MRZ and/or upload a document image)
  GET  /api/sessions          recent screenings
  GET  /api/sessions/{id}     one screening's full Evidence object
  POST /api/sessions/{id}/decision   officer Approve/Refer/Deny (linked ledger record)
  GET  /api/ledger            the audit ledger (hash-chained records)
  GET  /api/ledger/verify     recompute chain integrity + Merkle root
  POST /api/ledger/tamper-demo  DEMO: mutate a record so the chain visibly breaks
"""
from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, File, Form, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, Response

from .config import settings
from .core import mrz as mrzlib
from .core.ledger import Ledger
from .core.orchestrator import Screener
from .core.selftest import run_selftest
from .core.types import ScreenInputs
from .storage.db import get_store

STATIC_DIR = Path(__file__).parent / "static"
state: dict = {}


@asynccontextmanager
async def lifespan(app: FastAPI):
    store = await get_store()
    ledger = Ledger(store, settings.LEDGER_SECRET)
    state["store"] = store
    state["ledger"] = ledger
    state["screener"] = Screener(store, ledger)
    # Seed a MOCK watchlist (real LOC / Interpol SLTD are BoI/CBI-side and restricted).
    for entry in (
        {"value": "L898902C3", "type": "doc_number", "reason": "MOCK: reported lost/stolen (Interpol SLTD demo)"},
        {"value": "Z1234567", "type": "doc_number", "reason": "MOCK: lookout circular (demo)"},
    ):
        await store.watchlist_add(entry)
    print(f"[startup] NEBULA screening API | storage backend = {store.backend} "
          f"| config = {settings.CONFIG_VERSION}")
    # Warm the face model in the background so the first screening isn't slow (non-blocking).
    try:
        from .core import face as face_mod
        if face_mod.available():
            asyncio.create_task(asyncio.to_thread(face_mod.warm))
    except Exception as exc:  # pragma: no cover
        print(f"[startup] face warm-up skipped: {exc}")
    yield


app = FastAPI(title="NEBULA Screening API", version="0.1.0", lifespan=lifespan)


@app.get("/", response_class=HTMLResponse)
async def index():
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/api/health")
async def health():
    return {"status": "ok", "storage": state["store"].backend,
            "config_version": settings.CONFIG_VERSION, "station": settings.STATION_ID}


@app.get("/api/selftest")
async def selftest():
    return await run_selftest()


@app.get("/api/sample")
async def sample(variant: str = "valid"):
    """Return a legal synthetic passport MRZ for the demo."""
    return mrzlib.sample_passport(tampered=(variant == "tampered"))


@app.post("/api/mrz-correct")
async def mrz_correct_ep(line1: str = Form(""), line2: str = Form(""), line3: str = Form("")):
    """Demo the OCR-correction pipeline: noisy MRZ lines → corrected + validated."""
    from .core import mrz_correct
    lines = [l for l in (line1, line2, line3) if l.strip()]
    return mrz_correct.correct_mrz(lines)


@app.post("/api/screen")
async def screen(
    mrz_line1: str = Form(""),
    mrz_line2: str = Form(""),
    mrz_line3: str = Form(""),
    doc_type: str = Form("PASSPORT"),
    printed_dob: str = Form(""),
    printed_doc_number: str = Form(""),
    printed_expiry: str = Form(""),
    chip_mode: str = Form("none"),
    border: str = Form(""),
    direction: str = Form(""),
    traveler_nationality: str = Form(""),
    mode: str = Form(""),
    age_band: str = Form(""),
    document: Optional[UploadFile] = File(None),
    live_face: Optional[UploadFile] = File(None),
):
    printed = {}
    if printed_dob:
        printed["dob"] = printed_dob
    if printed_doc_number:
        printed["doc_number"] = printed_doc_number
    if printed_expiry:
        printed["expiry"] = printed_expiry

    doc_bytes = await document.read() if document is not None else None
    live_bytes = await live_face.read() if live_face is not None else None
    inputs = ScreenInputs(
        doc_type=doc_type,
        mrz_lines=[l for l in (mrz_line1, mrz_line2, mrz_line3) if l.strip()],
        printed=printed,
        document_bytes=doc_bytes,
        document_filename=document.filename if document is not None else None,
        live_face_bytes=live_bytes,
        chip_present=(chip_mode != "none"),
        chip_mode=chip_mode,
        border=border or None,
        direction=direction or None,
        traveler_nationality=traveler_nationality or None,
        mode=mode or None,
        age_band=age_band or None,
    )
    ev = await state["screener"].screen(inputs)
    return JSONResponse(ev.model_dump(mode="json"))


@app.get("/api/blob")
async def blob(ref: str):
    """Serve a stored blob (e.g. a tamper heatmap PNG) by its ref."""
    data = await state["store"].get_blob(ref)
    if data is None:
        return JSONResponse({"error": "not found"}, status_code=404)
    return Response(content=data, media_type="image/png")


@app.get("/api/sessions")
async def sessions(limit: int = 50):
    return await state["store"].list_sessions(limit)


@app.get("/api/sessions/{sid}")
async def session(sid: str):
    doc = await state["store"].get_session(sid)
    return doc or JSONResponse({"error": "not found"}, status_code=404)


@app.post("/api/sessions/{sid}/decision")
async def decide(sid: str, action: str = Form(...), officer_id: str = Form(""), reason: str = Form("")):
    # Officer is never blocked — MANUAL_VERIFY works even on a failed/HIGH screening (IFA-2025 s.3).
    ev = await state["screener"].decide(sid, action, officer_id or None, reason or None)
    if ev is None:
        return JSONResponse({"error": "not found"}, status_code=404)
    return ev.model_dump(mode="json")


@app.get("/api/ledger")
async def ledger_all():
    return await state["ledger"].all()


@app.get("/api/ledger/verify")
async def ledger_verify():
    return await state["ledger"].verify()


@app.post("/api/ledger/tamper-demo")
async def ledger_tamper(seq: int = Form(0)):
    # DEMO ONLY + destructive: mutates a stored record so the chain visibly breaks.
    return await state["ledger"].demo_tamper(seq)


@app.get("/api/watchlist")
async def watchlist():
    return await state["store"].watchlist_all()


@app.post("/api/watchlist")
async def watchlist_add(value: str = Form(...), reason: str = Form(""), type: str = Form("doc_number")):
    await state["store"].watchlist_add({"value": value, "type": type, "reason": reason or "added by officer"})
    return {"ok": True, "count": len(await state["store"].watchlist_all())}


@app.get("/api/oversight")
async def oversight():
    """Accountability view: officer decisions that OVERRODE the system (cleared a non-clean case)."""
    led = await state["ledger"].all()
    overrides = [
        {"seq": r.get("seq"), "session_id": r.get("session_id"), "at": r.get("timestamp"),
         "officer_id": (r.get("verdict") or {}).get("officer_id"),
         "action": (r.get("verdict") or {}).get("officer_action"),
         "reason": (r.get("verdict") or {}).get("reason"),
         "system_band": (r.get("verdict") or {}).get("system_band"),
         "system_gate": (r.get("verdict") or {}).get("system_gate")}
        for r in led
        if r.get("event") == "OFFICER_DECISION" and (r.get("verdict") or {}).get("override")
    ]
    return {"override_count": len(overrides), "overrides": overrides}
