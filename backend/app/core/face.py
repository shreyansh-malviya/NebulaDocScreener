"""Face detection + ArcFace embedding via InsightFace buffalo_l (CPU).

REAL matcher (verified: same-face cosine ~1.0, different-face ~0.06). Everything is
guarded so that if insightface / the model is unavailable, the module ABSTAINS rather
than crashing (reliability-first). The model (buffalo_l ~280MB) auto-downloads once to
backend/models_cache/ and is then fully offline.
"""
from __future__ import annotations

import os
import threading
from pathlib import Path
from typing import Optional

import numpy as np

# backend/models_cache (gitignored); override with FACE_MODELS_ROOT
_MODELS_ROOT = os.getenv("FACE_MODELS_ROOT") or str(Path(__file__).resolve().parents[2] / "models_cache")

_app = None
_lock = threading.Lock()


def available() -> bool:
    try:
        import cv2  # noqa: F401
        import insightface  # noqa: F401
        return True
    except Exception:
        return False


def _get_app():
    global _app
    if _app is None:
        with _lock:
            if _app is None:
                from insightface.app import FaceAnalysis
                app = FaceAnalysis(name="buffalo_l", root=_MODELS_ROOT,
                                   providers=["CPUExecutionProvider"])
                app.prepare(ctx_id=-1, det_size=(640, 640))
                _app = app
    return _app


def warm() -> bool:
    """Pre-load the model (called in a background thread at startup)."""
    try:
        _get_app()
        return True
    except Exception as exc:  # pragma: no cover
        print(f"[face] warm-up failed: {exc}")
        return False


def embed(image_bytes: bytes) -> dict:
    """Detect the largest face and return its normalised 512-D embedding."""
    try:
        import cv2
        app = _get_app()
        img = cv2.imdecode(np.frombuffer(image_bytes, np.uint8), cv2.IMREAD_COLOR)
        if img is None:
            return {"ok": False, "reason": "undecodable image"}
        faces = app.get(img)
        if not faces:
            return {"ok": False, "reason": "no_face"}
        f = max(faces, key=lambda x: (x.bbox[2] - x.bbox[0]) * (x.bbox[3] - x.bbox[1]))
        return {"ok": True, "embedding": np.asarray(f.normed_embedding, dtype=float).tolist(),
                "det_score": float(f.det_score), "bbox": [int(v) for v in f.bbox]}
    except Exception as exc:
        return {"ok": False, "reason": f"error: {type(exc).__name__}: {exc}"}


def cosine(a, b) -> float:
    va, vb = np.asarray(a, dtype=float), np.asarray(b, dtype=float)
    na, nb = np.linalg.norm(va), np.linalg.norm(vb)
    if na == 0 or nb == 0:
        return 0.0
    return float(np.dot(va, vb) / (na * nb))
