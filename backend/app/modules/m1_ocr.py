"""Module 1 — OCR / MRZ extraction.

REAL path: MRZ text is parsed + check-digits computed via core.mrz (offline, no deps).
STUB path: a document *image* is accepted and stored, but image OCR (fastmrz + PaddleOCR)
           is pending the Tesseract install — clearly labelled, never faked.
"""
from __future__ import annotations

from ..core import mrz as mrzlib
from ..core import mrz_correct, ocr
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

    # ---- IMAGE: ONNX OCR (RapidOCR) -> correction pipeline -> validate ----
    if inputs.document_bytes:
        if not ocr.available():
            m1.status = "STUB"
            m1.source = "image_pending"
            m1.notes.append("OCR engine not installed (rapidocr-onnxruntime). Paste MRZ text to validate now.")
            return m1
        read = ocr.read_mrz(inputs.document_bytes)
        if not read["lines"]:
            m1.status = "LOW_QUALITY"
            m1.source = "rapidocr"
            m1.notes.append(f"No MRZ detected in image ({read.get('reason', 'no MRZ-like lines')}). Request re-scan.")
            return m1
        corr = mrz_correct.correct_mrz(read["lines"])
        parsed = mrzlib.parse_mrz(corr["corrected_lines"])
        avg_conf = (sum(read["confidences"]) / len(read["confidences"])) if read["confidences"] else 0.0
        m1.source = "rapidocr"
        m1.mrz = MRZData(
            present=bool(parsed["format"]),
            format=parsed["format"],
            lines=corr["corrected_lines"],
            fields=parsed["fields"],
            raw_check_digits=parsed["raw_check_digits"],
            computed_check_digits=parsed["computed_check_digits"],
        )
        m1.status = "OK" if parsed["format"] else "LOW_QUALITY"
        m1.notes.append(f"MRZ read via RapidOCR (ONNX), avg confidence {avg_conf:.2f}; "
                        f"OCR corrections applied: {corr['num_corrections']}.")
        if corr["ambiguous_fields"]:
            m1.notes.append("Ambiguous check-digit repair on " + ", ".join(corr["ambiguous_fields"])
                            + " — recommend manual review.")
        return m1

    m1.status = "FAILED"
    m1.notes.append("No MRZ text and no document image provided.")
    return m1
