"""Risk fusion engine — the deterministic verdict.

Two tiers (see Rough/research/05-INTERNAL-DESIGN.md §4):
  Tier 1  hard-rule GATES that OVERRIDE everything (a cryptographic/checksum failure can
          never be "averaged away").
  Tier 2  a transparent weighted soft-score over the AVAILABLE signals, else ABSTAIN.

Pure function of the Evidence + config → reproducible, explainable, no black box.
"""
from __future__ import annotations

from ..config import settings
from ..models import Contribution, Evidence, Fusion

# risk-band ordering, so we can take a "floor" (e.g. expired => at least MEDIUM)
_RANK = {"LOW": 0, "REVIEW": 1, "MEDIUM": 2, "HIGH": 3}


def _clamp01(x: float) -> float:
    return max(0.0, min(1.0, x))


def _band_from_score(score: float, cfg) -> str:
    if score >= cfg.BAND_HIGH:
        return "HIGH"
    if score >= cfg.BAND_MED:
        return "MEDIUM"
    return "LOW"


def _action(band: str) -> str:
    return {
        "HIGH": "Mandatory secondary inspection + supervisor (ADVISORY).",
        "MEDIUM": "Officer review with highlighted concerns (ADVISORY).",
        "LOW": "Advisory clear — officer present (ADVISORY).",
        "REVIEW": "Manual review — insufficient/low-quality evidence to score (ADVISORY).",
    }.get(band, "Manual review (ADVISORY).")


def fuse(ev: Evidence, cfg=settings) -> Fusion:
    m2, m4, m5 = ev.m2_validation, ev.m4_face, ev.m5_chip

    # ---------------- Tier 1: hard gates (deterministic overrides) ----------------
    # Chip Passive Authentication failed => cryptographic proof of tampering/forgery.
    if (m5.passive_auth or {}).get("result") == "FAIL":
        return Fusion(gate_fired="CHIP_PA_FAIL", risk=1.0, band="HIGH",
                      recommended_action=_action("HIGH"),
                      contributions=[Contribution(signal="chip.passive_auth", risk=1.0, weight="GATE")])

    # Any MRZ check-digit failure => document self-inconsistent.
    failed_cd = [k for k, v in (m2.checksums or {}).items() if v is False]
    if failed_cd:
        return Fusion(gate_fired="MRZ_CHECKSUM_FAIL", risk=0.95, band="HIGH",
                      recommended_action=_action("HIGH"),
                      contributions=[Contribution(signal=f"mrz.checksum.{k}", risk=0.95, weight="GATE")
                                     for k in failed_cd])

    # Presentation attack at the live camera.
    if (m4.liveness or {}).get("label") == "SPOOF":
        return Fusion(gate_fired="LIVENESS_SPOOF", risk=0.9, band="HIGH",
                      recommended_action=_action("HIGH"),
                      contributions=[Contribution(signal="face.liveness", risk=0.9, weight="GATE")])

    # Chip Active Authentication failed => possible clone.
    if (m5.active_auth or {}).get("result") == "FAIL":
        return Fusion(gate_fired="CHIP_CLONE", risk=0.9, band="HIGH",
                      recommended_action=_action("HIGH"),
                      contributions=[Contribution(signal="chip.active_auth", risk=0.9, weight="GATE")])

    # Watchlist / lost-stolen hit => HIGH (known-bad document or person).
    if ev.records.watchlist_hit:
        return Fusion(gate_fired="WATCHLIST_HIT", risk=0.95, band="HIGH",
                      recommended_action=_action("HIGH"),
                      contributions=[Contribution(signal="records.watchlist", risk=0.95, weight="GATE")])

    # Expired document => at least MEDIUM (floor, not a hard HIGH).
    floor = "MEDIUM" if m2.expiry_state == "EXPIRED" else "LOW"
    # Document not accepted for this crossing (per SSB/BoI policy) => at least MEDIUM.
    if m2.document_accepted is False and _RANK["MEDIUM"] > _RANK[floor]:
        floor = "MEDIUM"
    # Multiple-identity / photo-swap alert => at least MEDIUM.
    if ev.records.identity_alerts and _RANK["MEDIUM"] > _RANK[floor]:
        floor = "MEDIUM"
    # Cross-document identity mismatch (name/DOB, e.g. passport↔visa) => at least MEDIUM.
    _cm = m2.cross_match or {}
    if _cm.get("checked") and _cm.get("consistent") is False and _RANK["MEDIUM"] > _RANK[floor]:
        floor = "MEDIUM"

    # ---------------- Tier 2: soft fusion over AVAILABLE signals ----------------
    w = cfg.FUSION_WEIGHTS
    parts: list[tuple[str, float, float]] = []  # (name, risk, weight)

    if ev.m3_tamper.fused_score is not None:
        parts.append(("tamper", _clamp01(ev.m3_tamper.fused_score), w["tamper"]))

    viz = {k: v for k, v in (m2.viz_mrz_match or {}).items() if v is not None}
    if viz:
        frac_mismatch = sum(1 for v in viz.values() if v is False) / len(viz)
        parts.append(("viz_mismatch", frac_mismatch, w["viz_mismatch"]))

    if m2.document_accepted is False:
        parts.append(("not_accepted", 0.8, w["acceptance"]))

    if ev.records.identity_alerts:
        parts.append(("identity_alert", 0.75, w["identity"]))

    if _cm.get("checked") and _cm.get("consistent") is False:
        parts.append(("cross_doc_mismatch", 0.8, w["cross_doc"]))

    if m4.similarity is not None:
        hi, lo = cfg.FACE_TAU_HI, cfg.FACE_TAU_LO
        if hi > lo:
            face_risk = 1.0 - _clamp01((m4.similarity - lo) / (hi - lo))
        else:
            face_risk = 0.0 if m4.similarity >= hi else 1.0
        parts.append(("face", face_risk, w["face"]))

    if m5.status == "ABSENT":
        # absence of a chip is not guilt, only a small prior (SSB land-border reality).
        parts.append(("chip_absent", 0.15, w["chip_absent"]))

    adv = m4.advisory or {}
    adv_max = max([adv.get("deepfake_suspicion") or 0.0, adv.get("morph_suspicion") or 0.0], default=0.0)
    if adv_max > 0:
        parts.append(("advisory", 0.3 * adv_max, w["advisory"]))  # capped; experimental

    total_weight = sum(w.values())
    avail_weight = sum(p[2] for p in parts)
    # A validated MRZ (we are in Tier 2, so its check digits PASSED) is itself strong
    # positive evidence of a self-consistent document — enough to render a verdict.
    core_present = bool(m2.checksums)

    contributions = [Contribution(signal=name, risk=round(risk, 4), weight=weight)
                     for name, risk, weight in parts]

    soft = (sum(risk * weight for _, risk, weight in parts) / avail_weight) if avail_weight > 0 else 0.0
    soft = _clamp01(soft)
    band = _band_from_score(soft, cfg)

    # ABSTAIN only when we cannot confidently CLEAR a document: little evidence AND low risk.
    # A high risk signal is always surfaced (never hidden behind "review").
    confident = core_present or (avail_weight >= cfg.MIN_SIGNAL_WEIGHT * total_weight)
    abstain = False
    if not confident and band == "LOW":
        band, abstain = "REVIEW", True

    if _RANK[floor] > _RANK[band]:
        band = floor

    return Fusion(gate_fired=None, soft_score=round(soft, 4), risk=round(soft, 4), band=band,
                  abstain=abstain, contributions=contributions, recommended_action=_action(band))
