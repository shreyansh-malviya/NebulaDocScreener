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

from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, File, Form, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse

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
    print(f"[startup] NEBULA screening API | storage backend = {store.backend} "
          f"| config = {settings.CONFIG_VERSION}")
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
    document: Optional[UploadFile] = File(None),
):
    printed = {}
    if printed_dob:
        printed["dob"] = printed_dob
    if printed_doc_number:
        printed["doc_number"] = printed_doc_number
    if printed_expiry:
        printed["expiry"] = printed_expiry

    doc_bytes = await document.read() if document is not None else None
    inputs = ScreenInputs(
        doc_type=doc_type,
        mrz_lines=[l for l in (mrz_line1, mrz_line2, mrz_line3) if l.strip()],
        printed=printed,
        document_bytes=doc_bytes,
        document_filename=document.filename if document is not None else None,
        chip_present=(chip_mode != "none"),
        chip_mode=chip_mode,
    )
    ev = await state["screener"].screen(inputs)
    return JSONResponse(ev.model_dump(mode="json"))


@app.get("/api/sessions")
async def sessions(limit: int = 50):
    return await state["store"].list_sessions(limit)


@app.get("/api/sessions/{sid}")
async def session(sid: str):
    doc = await state["store"].get_session(sid)
    return doc or JSONResponse({"error": "not found"}, status_code=404)


@app.post("/api/sessions/{sid}/decision")
async def decide(sid: str, action: str = Form(...)):
    ev = await state["screener"].decide(sid, action)
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
