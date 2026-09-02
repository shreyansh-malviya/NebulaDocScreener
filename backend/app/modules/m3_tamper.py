"""Module 3 — Tamper / forgery forensics.

REAL classical bank now (copy-move + ELA + metadata via core.forensics — CPU, no GPU).
Each signal contributes a weighted score + a heatmap (stored as a blob, referenced by the
Evidence). Fused by noisy-OR + spatial agreement. The strong DL localizer (TruFor/CAT-Net)
is added later behind a GPU-with-CPU-fallback guard, so this module always produces output.
"""
from __future__ import annotations

from ..core import forensics
from ..core.types import ScreenInputs
from ..models import M3Tamper, TamperSignal


async def run(inputs: ScreenInputs, store) -> M3Tamper:
    m3 = M3Tamper()

    if not inputs.document_bytes:
        m3.status = "STUB"
        m3.fused_score = None       # no image → contributes no signal (fusion skips it)
        m3.notes.append("No document image provided; paste MRZ for the deterministic checks.")
        return m3

    try:
        raw_signals = forensics.analyze(inputs.document_bytes)
    except Exception as exc:
        m3.status = "FAILED"
        m3.fused_score = None
        m3.notes.append(f"forensics error → abstain: {type(exc).__name__}: {exc}")
        return m3

    signals: list[TamperSignal] = []
    for s in raw_signals:
        ref = None
        if s.get("heatmap"):
            ref, _ = await store.put_blob(s["heatmap"], {"kind": "heatmap", "signal": s["name"]})
        signals.append(TamperSignal(name=s["name"], score=s["score"], regions=s["regions"],
                                    heatmap_ref=ref, weight=s["weight"], note=s.get("note")))

    fused, agreement = forensics.fuse_scores(raw_signals)
    m3.signals = signals
    m3.fused_score = fused
    m3.spatial_agreement = agreement
    m3.status = "CLASSICAL_ONLY"
    # region→field mapping needs image-OCR field boxes (Week 2); left empty for now.
    m3.notes.append("Classical bank (copy-move + ELA + metadata). DL localizer (TruFor) pending GPU wiring.")
    return m3
