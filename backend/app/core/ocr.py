"""ONNX MRZ OCR via RapidOCR (PP-OCR models on onnxruntime).

Chosen for deployability: pure onnxruntime (no PyTorch, no Paddle, no system binary),
models bundled in the package (~30 MB), CPU-only — fits Render's free tier. Reads the raw
MRZ characters + per-character confidence; core.mrz_correct then cleans them up. Guarded so
the app degrades gracefully (M1 image path → LOW_QUALITY) if the engine isn't installed.
"""
from __future__ import annotations

import re
import threading

_engine = None
_lock = threading.Lock()

# MRZ lines are uppercase A–Z, 0–9 and '<' filler, ~30–44 chars.
_MRZ_CHARS = re.compile(r"[^A-Z0-9<]")
_MRZ_LINE = re.compile(r"^[A-Z0-9<]{28,}$")


def available() -> bool:
    try:
        import cv2  # noqa: F401
        import rapidocr_onnxruntime  # noqa: F401
        return True
    except Exception:
        return False


def _get_engine():
    global _engine
    if _engine is None:
        with _lock:
            if _engine is None:
                from rapidocr_onnxruntime import RapidOCR
                _engine = RapidOCR()
    return _engine


def warm() -> bool:
    try:
        _get_engine()
        return True
    except Exception as exc:  # pragma: no cover
        print(f"[ocr] warm-up failed: {exc}")
        return False


def read_mrz(image_bytes: bytes, max_side: int = 1600) -> dict:
    """Detect + read the MRZ lines from a document image.
    Returns {lines: [...], confidences: [...]} (lines top-to-bottom)."""
    try:
        import cv2
        import numpy as np

        img = cv2.imdecode(np.frombuffer(image_bytes, np.uint8), cv2.IMREAD_COLOR)
        if img is None:
            return {"lines": [], "confidences": [], "reason": "undecodable image"}
        # cap size to bound memory on small hosts (Render free tier = 512 MB)
        h, w = img.shape[:2]
        if max(h, w) > max_side:
            s = max_side / max(h, w)
            img = cv2.resize(img, (int(w * s), int(h * s)), interpolation=cv2.INTER_AREA)
        result, _ = _get_engine()(img)
        if not result:
            return {"lines": [], "confidences": []}

        # keep only MRZ-looking text, ordered top-to-bottom (MRZ sits at the page bottom)
        items = sorted(result, key=lambda r: r[0][0][1])
        lines, confs = [], []
        for box, text, score in items:
            cleaned = _MRZ_CHARS.sub("", text.upper().replace(" ", ""))
            if _MRZ_LINE.match(cleaned):
                lines.append(cleaned)
                confs.append(float(score))
        # the MRZ is the last 2–3 such lines
        return {"lines": lines[-3:], "confidences": confs[-3:]}
    except Exception as exc:
        return {"lines": [], "confidences": [], "reason": f"error: {type(exc).__name__}: {exc}"}
