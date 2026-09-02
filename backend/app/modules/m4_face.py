"""Module 4 — Face verification (document photo vs live capture).

REAL matcher via core.face (InsightFace ArcFace, CPU). Reports cosine SIMILARITY and a
3-zone verdict (ACCEPT / REVIEW / REJECT) with thresholds from config (calibrate on a real
ID↔selfie set). Degrades to NO_FACE/abstain if a face isn't found or insightface is absent.
Liveness (Silent-Face) is a later add — noted, not faked.
"""
from __future__ import annotations

from ..config import settings
from ..core import face
from ..core.types import ScreenInputs
from ..models import M4Face


async def run(inputs: ScreenInputs) -> M4Face:
    m4 = M4Face()
    doc, live = inputs.document_bytes, inputs.live_face_bytes

    if not doc and not live:
        m4.status = "NO_FACE"
        m4.notes.append("No document image or live capture provided.")
        return m4

    if not face.available():
        m4.status = "FAILED"
        m4.notes.append("insightface unavailable → abstain (install requirements-ml.txt).")
        return m4

    if not (doc and live):
        which = "document" if doc else "live"
        res = face.embed(doc or live)
        m4.status = "OK" if res["ok"] else "NO_FACE"
        if which == "document" and res["ok"]:
            m4.doc_embedding = res["embedding"]          # feed the identity gallery
        m4.notes.append(f"Only the {which} image was provided; both document photo and live "
                        f"capture are needed to match (face detected={res['ok']}).")
        return m4

    ed, el = face.embed(doc), face.embed(live)
    if not ed["ok"] or not el["ok"]:
        m4.status = "NO_FACE"
        m4.notes.append(f"Face not detected (document={ed.get('reason', 'ok')}, live={el.get('reason', 'ok')}).")
        return m4

    m4.doc_embedding = ed["embedding"]                    # document face template → gallery
    sim = face.cosine(ed["embedding"], el["embedding"])
    m4.similarity = round(sim, 4)
    m4.threshold = settings.FACE_TAU_HI
    if sim >= settings.FACE_TAU_HI:
        m4.match_zone = "ACCEPT"
    elif sim < settings.FACE_TAU_LO:
        m4.match_zone = "REJECT"
    else:
        m4.match_zone = "REVIEW"
    m4.status = "OK"
    m4.notes.append(
        f"ArcFace cosine similarity {sim:.3f} → {m4.match_zone} "
        f"(τ_hi={settings.FACE_TAU_HI}, τ_lo={settings.FACE_TAU_LO}; calibrate on real ID↔selfie set). "
        "Liveness (Silent-Face) pending."
    )
    return m4
