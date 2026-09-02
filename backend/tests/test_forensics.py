"""Real tests for the classical forensics bank (Module 3), using synthetic images."""
import io

import numpy as np
from PIL import Image

from app.core import forensics


def _doc(duplicate: bool = False) -> bytes:
    """A document-like image with a textured 'stamp' patch; duplicate=True copy-moves it."""
    im = Image.new("RGB", (600, 400), (235, 235, 235))
    rng = np.random.default_rng(7)
    patch = Image.fromarray(rng.integers(0, 255, (64, 64, 3), dtype=np.uint8))
    im.paste(patch, (110, 110))
    if duplicate:
        im.paste(patch, (420, 260))   # same patch pasted again → copy-move
    buf = io.BytesIO()
    im.save(buf, "JPEG", quality=92)
    return buf.getvalue()


def test_copy_move_detects_duplicate():
    clean = forensics.copy_move(_doc(False))
    tampered = forensics.copy_move(_doc(True))
    assert tampered["score"] > clean["score"]
    assert tampered["score"] >= 0.3
    assert tampered["regions"]          # a bounding region was localised


def test_analyze_returns_full_bank_and_fuses():
    sigs = forensics.analyze(_doc(True))
    names = {s["name"] for s in sigs}
    assert {"copy_move", "ela", "metadata"} <= names
    fused, agreement = forensics.fuse_scores(sigs)
    assert 0.0 <= fused <= 1.0
    for s in sigs:
        assert 0.0 <= s["score"] <= 1.0
