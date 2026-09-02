"""Tests for the document-acceptance policy (SSB/BoI criteria) + its effect on fusion."""
from app.core import policy
from app.core.fusion import fuse
from app.models import Evidence


def test_aadhaar_not_a_travel_document():
    r = policy.check_acceptance("AADHAAR", "IND", "NEPAL", "LAND", "ADULT")
    assert r["accepted"] is False


def test_pan_and_dl_rejected():
    assert policy.check_acceptance("PAN", "IND", "BHUTAN", "LAND", "ADULT")["accepted"] is False
    assert policy.check_acceptance("DRIVING_LICENSE", "IND", "NEPAL", "LAND", "ADULT")["accepted"] is False


def test_passport_and_voter_id_accepted():
    assert policy.check_acceptance("PASSPORT", "IND", "NEPAL", "LAND", "ADULT")["accepted"] is True
    assert policy.check_acceptance("VOTER_ID", "IND", "BHUTAN", "LAND", "ADULT")["accepted"] is True


def test_third_country_needs_passport():
    assert policy.check_acceptance("VOTER_ID", "USA", "NEPAL", "AIR", "ADULT")["accepted"] is False
    assert policy.check_acceptance("PASSPORT", "USA", "NEPAL", "AIR", "ADULT")["accepted"] is True


def test_incomplete_context_not_evaluated():
    assert policy.check_acceptance("PASSPORT", None, None)["accepted"] is None


def test_fusion_not_accepted_raises_band():
    ev = Evidence()
    ev.m2_validation.checksums = {"doc_number": True, "dob": True, "expiry": True, "composite": True}
    ev.m2_validation.expiry_state = "VALID"
    ev.m2_validation.document_accepted = False
    f = fuse(ev)
    assert f.band in ("MEDIUM", "HIGH")
