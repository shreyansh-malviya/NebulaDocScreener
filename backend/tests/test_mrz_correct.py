"""Tests for the MRZ OCR-correction pipeline (positional + check-digit-guided)."""
from app.core import mrz, mrz_correct

VALID_L1 = "P<UTOERIKSSON<<ANNA<MARIA<<<<<<<<<<<<<<<<<<<"
VALID_L2 = "L898902C36UTO7408122F1204159ZE184226B<<<<<10"


def test_positional_confusions_corrected():
    bad = list(VALID_L2)
    bad[12] = "0"    # nationality UTO -> UT0 (alpha slot; 0 must become O)
    bad[15] = "O"    # DOB 740812: '0' -> 'O' (numeric slot; must become 0)
    bad[17] = "I"    # DOB: '1' -> 'I' (numeric slot; must become 1)
    bad = "".join(bad)
    assert mrz.parse_mrz([VALID_L1, bad])["valid"] is False
    res = mrz_correct.correct_mrz([VALID_L1, bad])
    assert res["valid_after"] is True
    assert res["corrected_lines"][1] == VALID_L2
    assert res["num_corrections"] >= 3


def test_check_digit_unique_repair():
    # DOB 740812 -> 740612 (8->6, a digit-digit confusion positional can't fix).
    # Only ONE confusable swap satisfies the check digit, so it is auto-corrected.
    bad = VALID_L2[:16] + "6" + VALID_L2[17:]
    assert mrz.parse_mrz([VALID_L1, bad])["valid"] is False
    res = mrz_correct.correct_mrz([VALID_L1, bad])
    assert res["valid_after"] is True
    assert res["corrected_lines"][1] == VALID_L2


def test_ambiguous_repair_is_flagged_not_miscorrected():
    # Document number '0' -> 'O': multiple confusable swaps satisfy the check digit.
    # The corrector must NOT silently pick a wrong one — it flags the field ambiguous.
    bad = VALID_L2[:5] + "O" + VALID_L2[6:]
    res = mrz_correct.correct_mrz([VALID_L1, bad])
    assert "doc_number" in res["ambiguous_fields"]
    assert res["corrected_lines"][1] != "L0989O2C36UTO7408122F1204159ZE184226B<<<<<10"


def test_does_not_mask_tampering():
    # A deliberate tamper (DOB 9->8) is NOT a visual OCR confusion, so it must stay invalid.
    t = mrz.sample_passport(tampered=True)
    res = mrz_correct.correct_mrz([t["line1"], t["line2"]])
    assert res["valid_after"] is False
