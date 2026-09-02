"""Module 1 — OCR / MRZ extraction.

REAL path: MRZ text is parsed + check-digits computed via core.mrz (offline, no deps).
STUB path: a document *image* is accepted and stored, but image OCR (fastmrz + PaddleOCR)
           is pending the Tesseract install — clearly labelled, never faked.
"""
from __future__ import annotations

from ..core import mrz as mrzlib
from ..core.types import ScreenInputs
from ..models import M1OCR, MRZData


async def run(inputs: ScreenInputs) -> M1OCR:
    m1 = M1OCR()

    # ---- REAL: MRZ text provided -> deterministic parse + checksum computation ----
    if inputs.mrz_lines:
        parsed = mrzlib.parse_mrz(inputs.mrz_lines)
        m1.source = "mrz_text"
        m1.mrz = MRZData(
            present=bool(parsed["format"]),
            format=parsed["format"],
            lines=[l.strip() for l in inputs.mrz_lines if l.strip()],
            fields=parsed["fields"],
            raw_check_digits=parsed["raw_check_digits"],
            computed_check_digits=parsed["computed_check_digits"],
        )
        if inputs.printed:
            m1.viz = dict(inputs.printed)   # printed fields for the MRZ<->VIZ cross-check (Module 2)
        if parsed["format"]:
            m1.status = "OK"
        else:
            m1.status = "FAILED"
            m1.notes.append("MRZ not recognised: " + "; ".join(parsed["errors"]))
        return m1

    # ---- STUB: image only (no MRZ text) -> pending real OCR ----
    if inputs.document_bytes:
        m1.status = "STUB"
        m1.source = "image_pending"
        m1.notes.append(
            "Image OCR pending (Module 1 image path needs Tesseract + fastmrz + PaddleOCR). "
            "Paste the MRZ text to run REAL offline validation now."
        )
        return m1

    m1.status = "FAILED"
    m1.notes.append("No MRZ text and no document image provided.")
    return m1
