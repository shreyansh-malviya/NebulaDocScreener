"""Shared input type for a screening request (kept dependency-light on purpose)."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class ScreenInputs:
    doc_type: str = "PASSPORT"
    mrz_lines: list[str] = field(default_factory=list)   # pasted MRZ (real validation path)
    printed: dict = field(default_factory=dict)          # printed VIZ fields for MRZ<->VIZ cross-check
    document_bytes: Optional[bytes] = None               # document image (image OCR path — pending)
    document_filename: Optional[str] = None
    live_face_bytes: Optional[bytes] = None
    chip_present: bool = False
