"""Real crypto tests for the simulated eMRTD chip (Module 5)."""
from app.core import emrtd
from app.core.fusion import fuse
from app.models import Evidence


def test_passive_auth_genuine_pass():
    chip = emrtd.issue_chip(b"DG1-MRZ", b"DG2-FACE", "genuine")
    pa = emrtd.passive_authentication(chip)
    assert pa["result"] == "PASS"
    assert pa["dsc_to_csca_chain"] is True
    assert pa["sod_signature"] is True
    assert all(pa["dg_hashes"].values())
    assert emrtd.active_authentication(chip)["result"] == "PASS"


def test_passive_auth_tampered_fail():
    chip = emrtd.issue_chip(b"DG1-MRZ", b"DG2-FACE", "tampered")
    pa = emrtd.passive_authentication(chip)
    assert pa["result"] == "FAIL"
    assert pa["dg_hashes"]["DG1"] is False   # the edited data group fails its hash


def test_cloned_active_auth_fail():
    chip = emrtd.issue_chip(b"DG1-MRZ", b"DG2-FACE", "cloned")
    assert emrtd.passive_authentication(chip)["result"] == "PASS"   # data intact
    assert emrtd.active_authentication(chip)["result"] == "FAIL"    # but cannot answer challenge


def test_fusion_gate_chip_pa_fail():
    ev = Evidence()
    ev.m5_chip.passive_auth = {"result": "FAIL"}
    f = fuse(ev)
    assert f.band == "HIGH" and f.gate_fired == "CHIP_PA_FAIL"


def test_fusion_gate_chip_clone():
    ev = Evidence()
    ev.m5_chip.passive_auth = {"result": "PASS"}
    ev.m5_chip.active_auth = {"result": "FAIL"}
    f = fuse(ev)
    assert f.band == "HIGH" and f.gate_fired == "CHIP_CLONE"
