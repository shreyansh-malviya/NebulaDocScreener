"""The Evidence Object — the single contract that flows through the pipeline.

Every module is a pure function that fills in ONE fragment of this object; the fusion
engine, the narrative, and the ledger read it at the end. Nothing else crosses module
boundaries (see Rough/research/05-INTERNAL-DESIGN.md §1). All fields have safe defaults
so PARTIAL evidence (a failed/abstained module) still produces a valid, judgeable object.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from pydantic import BaseModel, Field


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _uuid() -> str:
    return str(uuid.uuid4())


# ---------- capture / context ----------
class CaptureQuality(BaseModel):
    doc_blur: Optional[float] = None
    doc_glare: Optional[float] = None
    face_quality: Optional[float] = None


class Context(BaseModel):
    doc_type: str = "UNKNOWN"                    # PASSPORT | VISA | NATIONAL_ID | DRIVING_LICENSE | PERMIT | UNKNOWN
    doc_image_ref: Optional[str] = None          # blob ref (kept as ORIGINAL bytes)
    doc_image_sha256: Optional[str] = None        # integrity anchor for the ledger
    live_face_ref: Optional[str] = None
    chip_present: bool = False
    capture_quality: CaptureQuality = Field(default_factory=CaptureQuality)


# ---------- Module 1: OCR / MRZ ----------
class MRZData(BaseModel):
    present: bool = False
    format: Optional[str] = None                 # TD1 | TD2 | TD3
    lines: list[str] = Field(default_factory=list)
    fields: dict[str, Any] = Field(default_factory=dict)
    raw_check_digits: dict[str, str] = Field(default_factory=dict)
    computed_check_digits: dict[str, str] = Field(default_factory=dict)


class M1OCR(BaseModel):
    status: str = "PENDING"                      # OK | LOW_QUALITY | STUB | FAILED
    source: Optional[str] = None                 # mrz_text | fastmrz | paddleocr
    mrz: MRZData = Field(default_factory=MRZData)
    viz: dict[str, Any] = Field(default_factory=dict)         # printed fields (image OCR) — optional
    field_boxes: dict[str, Any] = Field(default_factory=dict)  # pixel boxes → used by M3 region mapping
    notes: list[str] = Field(default_factory=list)


# ---------- Module 2: Document validation (pure rules) ----------
class M2Validation(BaseModel):
    status: str = "PENDING"                      # OK | FAILED | SKIPPED
    checksums: dict[str, Optional[bool]] = Field(default_factory=dict)   # doc_number, dob, expiry, optional, composite
    expiry_state: Optional[str] = None           # VALID | EXPIRED | UNKNOWN
    country_code_valid: Optional[bool] = None
    date_logic_ok: Optional[bool] = None
    viz_mrz_match: dict[str, Optional[bool]] = Field(default_factory=dict)
    hard_fail: bool = False
    reasons: list[str] = Field(default_factory=list)


# ---------- Module 3: Tamper forensics ----------
class TamperSignal(BaseModel):
    name: str
    score: float = 0.0                           # 0..1 risk contribution
    regions: list[list[int]] = Field(default_factory=list)
    heatmap_ref: Optional[str] = None
    reliability: Optional[float] = None
    weight: float = 0.0
    note: Optional[str] = None


class M3Tamper(BaseModel):
    status: str = "PENDING"                      # OK | CLASSICAL_ONLY | STUB | FAILED
    signals: list[TamperSignal] = Field(default_factory=list)
    fused_score: Optional[float] = None
    spatial_agreement: bool = False
    tampered_fields: list[str] = Field(default_factory=list)
    fused_heatmap_ref: Optional[str] = None
    notes: list[str] = Field(default_factory=list)


# ---------- Module 4: Face (+ liveness, + advisory) ----------
class M4Face(BaseModel):
    status: str = "PENDING"                      # OK | NO_FACE | STUB | FAILED
    similarity: Optional[float] = None           # cosine SIMILARITY (not distance)
    threshold: Optional[float] = None
    match_zone: Optional[str] = None             # ACCEPT | REVIEW | REJECT
    liveness: dict[str, Any] = Field(default_factory=dict)     # {label, score}
    advisory: dict[str, Any] = Field(default_factory=dict)     # {deepfake_suspicion, morph_suspicion}
    notes: list[str] = Field(default_factory=list)


# ---------- Module 5: Chip PKI ----------
class M5Chip(BaseModel):
    status: str = "ABSENT"                        # VERIFIED | FAILED | ABSENT | UNREADABLE | STUB
    passive_auth: dict[str, Any] = Field(default_factory=dict)   # {sod_signature, dsc_to_csca_chain, dg_hashes, result}
    active_auth: dict[str, Any] = Field(default_factory=dict)    # {result}
    chip_vs_printed: dict[str, Any] = Field(default_factory=dict)
    notes: list[str] = Field(default_factory=list)


# ---------- Fusion (the verdict) ----------
class Contribution(BaseModel):
    signal: str
    risk: float
    weight: Any                                   # float, or the string "GATE"


class Fusion(BaseModel):
    gate_fired: Optional[str] = None
    soft_score: float = 0.0
    risk: float = 0.0
    band: str = "PENDING"                         # LOW | MEDIUM | HIGH | REVIEW | PENDING
    abstain: bool = False
    contributions: list[Contribution] = Field(default_factory=list)
    recommended_action: Optional[str] = None      # ADVISORY to a human — never auto-enforced


# ---------- Narrative / decision / ledger ----------
class Narrative(BaseModel):
    text: str = ""
    source: str = "template"                      # template | local | api
    grounded: bool = True


class Decision(BaseModel):
    officer_action: Optional[str] = None          # APPROVE | REFER | DENY
    at: Optional[datetime] = None


class LedgerRef(BaseModel):
    seq: Optional[int] = None
    prev_hash: Optional[str] = None
    record_hash: Optional[str] = None
    signature: Optional[str] = None


# ---------- top-level Evidence ----------
class Evidence(BaseModel):
    session_id: str = Field(default_factory=_uuid)
    created_at: datetime = Field(default_factory=_now)
    config_version: str = ""
    station_id: str = ""
    officer_id: Optional[str] = None

    context: Context = Field(default_factory=Context)
    m1_ocr: M1OCR = Field(default_factory=M1OCR)
    m2_validation: M2Validation = Field(default_factory=M2Validation)
    m3_tamper: M3Tamper = Field(default_factory=M3Tamper)
    m4_face: M4Face = Field(default_factory=M4Face)
    m5_chip: M5Chip = Field(default_factory=M5Chip)

    fusion: Fusion = Field(default_factory=Fusion)
    narrative: Narrative = Field(default_factory=Narrative)
    decision: Decision = Field(default_factory=Decision)
    ledger: LedgerRef = Field(default_factory=LedgerRef)

    module_timings: dict[str, float] = Field(default_factory=dict)
