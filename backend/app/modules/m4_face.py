"""Module 4 — Face verification + liveness.  [STUB — Week 2]

Clearly-labelled STUB: similarity=None (no face signal), liveness empty (no spoof claim).
The real matcher (InsightFace buffalo_l / ArcFace, CPU) + Silent-Face liveness lands Week 2
with a threshold CALIBRATED on real ID<->selfie pairs (cosine SIMILARITY, not distance).
"""
from __future__ import annotations

from ..core.types import ScreenInputs
from ..models import M4Face


async def run(inputs: ScreenInputs) -> M4Face:
    m4 = M4Face()
    m4.status = "STUB" if inputs.live_face_bytes else "NO_FACE"
    m4.similarity = None
    m4.liveness = {}
    m4.advisory = {}
    m4.notes.append("Face match + liveness pending (Week 2): InsightFace buffalo_l + Silent-Face.")
    return m4
