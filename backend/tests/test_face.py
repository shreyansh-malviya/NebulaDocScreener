"""Real tests for Module 4 face embedding/matching (skipped if insightface absent).
Uses insightface's OWN bundled sample image — no network image download."""
import pytest

from app.core import face

pytestmark = pytest.mark.skipif(not face.available(), reason="insightface not installed")


def _bundled_face_bytes() -> bytes:
    import cv2
    from insightface.data import get_image
    img = get_image("t1")               # bundled image with real faces
    ok, buf = cv2.imencode(".jpg", img)
    return buf.tobytes()


def test_embed_returns_512d_and_self_cosine_one():
    r = face.embed(_bundled_face_bytes())
    assert r["ok"] and len(r["embedding"]) == 512
    assert face.cosine(r["embedding"], r["embedding"]) > 0.99


def test_cosine_orthogonal_is_zero():
    assert abs(face.cosine([1.0, 0.0, 0.0], [0.0, 1.0, 0.0])) < 1e-6


def test_embed_no_face_on_blank():
    import cv2
    import numpy as np
    blank = np.full((200, 200, 3), 240, dtype=np.uint8)
    ok, buf = cv2.imencode(".jpg", blank)
    r = face.embed(buf.tobytes())
    assert r["ok"] is False and r["reason"] == "no_face"
