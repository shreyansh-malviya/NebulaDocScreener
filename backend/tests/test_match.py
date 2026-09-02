"""Tests for cross-document identity matching (name banded-fuzzy + DOB exact)."""
from app.core import match
from app.core.fusion import fuse
from app.models import Evidence


def test_name_order_independent_accept():
    s, band = match.match_names("ROHIT SHARMA", "SHARMA ROHIT")
    assert band == "ACCEPT" and s >= 0.9


def test_name_initial_tolerance():
    _, band = match.match_names("R SHARMA", "ROHIT SHARMA")
    assert band in ("ACCEPT", "REVIEW")


def test_name_mismatch():
    _, band = match.match_names("ROHIT SHARMA", "AMIT VERMA")
    assert band == "MISMATCH"


def test_dob_exact():
    assert match.match_dob("900101", "900101") is True
    assert match.match_dob("900101", "910101") is False


def test_cross_match_consistent_and_mismatch():
    ok = match.cross_match({"name": "SHARMA ROHIT", "dob": "900101"},
                           {"name": "ROHIT SHARMA", "dob": "900101"})
    assert ok["consistent"] is True
    bad = match.cross_match({"name": "SHARMA ROHIT", "dob": "900101"},
                            {"name": "ROHIT SHARMA", "dob": "880101"})
    assert bad["consistent"] is False


def test_fusion_cross_doc_mismatch_raises_band():
    ev = Evidence()
    ev.m2_validation.checksums = {"doc_number": True, "dob": True, "expiry": True, "composite": True}
    ev.m2_validation.expiry_state = "VALID"
    ev.m2_validation.cross_match = {"checked": True, "consistent": False, "reasons": ["DOB mismatch"]}
    f = fuse(ev)
    assert f.band in ("MEDIUM", "HIGH")
