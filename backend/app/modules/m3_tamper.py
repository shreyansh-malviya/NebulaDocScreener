"""Module 3 — Tamper / forgery forensics.  [STUB — Week 2]

Returns a clearly-labelled STUB that contributes NO signal (fused_score=None → the
fusion engine skips it). Nothing is faked. The real ensemble (copy-move SIFT + classical
bank + TruFor/CAT-Net via PhotoHolmes, with a classical-only CPU fallback) lands in Week 2.
"""
from __future__ import annotations

from ..core.types import ScreenInputs
from ..models import M3Tamper


async def run(inputs: ScreenInputs) -> M3Tamper:
    m3 = M3Tamper()
    m3.status = "STUB"
    m3.fused_score = None  # contributes no risk until the real detector is wired
    if inputs.document_bytes:
        m3.notes.append("Tamper forensics pending (Week 2): copy-move + classical bank + TruFor heatmap.")
    else:
        m3.notes.append("No document image provided for tamper analysis.")
    return m3
