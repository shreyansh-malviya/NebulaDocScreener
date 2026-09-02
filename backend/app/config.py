"""Configuration-as-data.

Every threshold / weight lives here (overridable by environment / .env), never
hard-coded across the codebase — so calibration is a config change and every verdict
is reproducible from a known config version.
"""
from __future__ import annotations

import os

from dotenv import load_dotenv

load_dotenv()  # load backend/.env if present; harmless if absent


def _f(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return default


class Settings:
    # --- identity / config version (stamped into every Evidence + ledger record) ---
    CONFIG_VERSION = "cfg-2026-09-02.1"
    STATION_ID = os.getenv("STATION_ID", "SSB-DEMO-LANE-1")

    # --- storage ---
    STORAGE_BACKEND = os.getenv("STORAGE_BACKEND", "memory").lower()  # memory | mongo
    MONGO_URI = os.getenv("MONGO_URI", "")
    MONGO_DB = os.getenv("MONGO_DB", "nebula_screening")

    # --- audit ledger ---
    LEDGER_SECRET = os.getenv("LEDGER_SECRET", "dev-insecure-station-key-change-me")

    # --- narrative ---
    LLM_NARRATIVE = os.getenv("LLM_NARRATIVE", "template").lower()  # template | local | api
    ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
    OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")

    # --- optional tesseract (MRZ image OCR) ---
    TESSERACT_CMD = os.getenv("TESSERACT_CMD", "")

    # --- per-module timeboxes (seconds) — degrade-to-abstain on timeout ---
    TIMEBOX = {
        "m1_ocr": 6.0,
        "m2_validation": 1.0,
        "m3_tamper": 8.0,
        "m4_face": 4.0,
        "liveness": 2.0,
        "m5_chip": 6.0,
    }

    # --- face verification thresholds (cosine SIMILARITY; calibrate on real ID<->selfie set) ---
    FACE_TAU_HI = _f("FACE_TAU_HI", 0.45)   # >= -> ACCEPT
    FACE_TAU_LO = _f("FACE_TAU_LO", 0.30)   # <  -> REJECT ; between -> REVIEW

    # --- risk fusion: soft-signal weights (only used when NO hard gate fires) ---
    FUSION_WEIGHTS = {
        "tamper": 0.40,
        "viz_mismatch": 0.20,
        "face": 0.30,
        "chip_absent": 0.05,
        "advisory": 0.05,
    }
    # risk band cut-points (0..1)
    BAND_HIGH = _f("BAND_HIGH", 0.70)   # >= -> HIGH
    BAND_MED = _f("BAND_MED", 0.35)     # >= -> MEDIUM ; else LOW
    # if less than this fraction of soft-signal weight is available -> abstain to manual review
    MIN_SIGNAL_WEIGHT = _f("MIN_SIGNAL_WEIGHT", 0.5)


settings = Settings()
