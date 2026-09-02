"""Reliability test for the ONNX OCR module (skipped if rapidocr not installed)."""
import cv2
import numpy as np
import pytest

from app.core import ocr

pytestmark = pytest.mark.skipif(not ocr.available(), reason="rapidocr-onnxruntime not installed")


def test_read_mrz_blank_is_graceful():
    blank = np.full((120, 400, 3), 255, dtype=np.uint8)
    ok, buf = cv2.imencode(".png", blank)
    r = ocr.read_mrz(buf.tobytes())
    assert r["lines"] == []      # no MRZ found, but no crash


def test_read_mrz_undecodable_is_graceful():
    r = ocr.read_mrz(b"not-an-image")
    assert r["lines"] == [] and "reason" in r
