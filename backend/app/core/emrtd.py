"""Simulated ICAO eMRTD chip + PKI — REAL cryptography (no physical passport needed).

This implements the actual verification mechanism of an e-passport chip (ICAO Doc 9303),
using real ECDSA signatures and an X.509 CSCA→DSC trust chain:

  * Passive Authentication (PA): the chip's EF.SOD holds a signed list of data-group hashes.
    We verify DSC→CSCA chain + EF.SOD signature + recompute each data-group hash. Any edit
    to a data group breaks its hash → cryptographic tamper detection.
  * Active Authentication (AA): challenge–response with a key that never leaves a genuine
    chip → detects a CLONE (which has the public data but not the private AA key).

For the demo we *synthesise* a genuine chip from the passport data and sign it with a
station-trusted CSCA. This demonstrates the exact crypto; in production the CSCA trust
anchors come from the ICAO PKD. See Rough/research/04-orchestration-blockchain-arch.md §2.1.
"""
from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Optional

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID

_CURVE = ec.SECP256R1()
_SIG = ec.ECDSA(hashes.SHA256())


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _name(cn: str, country: str = "IN") -> x509.Name:
    return x509.Name([
        x509.NameAttribute(NameOID.COUNTRY_NAME, country),
        x509.NameAttribute(NameOID.ORGANIZATION_NAME, "NEBULA Simulated PKI"),
        x509.NameAttribute(NameOID.COMMON_NAME, cn),
    ])


class TrustStore:
    """A simulated Country Signing CA (CSCA) that can issue Document Signer Certs (DSC)."""

    def __init__(self) -> None:
        self._csca_key = ec.generate_private_key(_CURVE)
        now = datetime.now(timezone.utc)
        self.csca_cert = (
            x509.CertificateBuilder()
            .subject_name(_name("CSCA-IND"))
            .issuer_name(_name("CSCA-IND"))                       # self-signed root
            .public_key(self._csca_key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(now - timedelta(days=1))
            .not_valid_after(now + timedelta(days=3650))
            .add_extension(x509.BasicConstraints(ca=True, path_length=1), critical=True)
            .sign(self._csca_key, hashes.SHA256())
        )

    def issue_dsc(self) -> tuple[ec.EllipticCurvePrivateKey, x509.Certificate]:
        dsc_key = ec.generate_private_key(_CURVE)
        now = datetime.now(timezone.utc)
        dsc_cert = (
            x509.CertificateBuilder()
            .subject_name(_name("DSC-IND-001"))
            .issuer_name(self.csca_cert.subject)                  # issued BY the CSCA
            .public_key(dsc_key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(now - timedelta(days=1))
            .not_valid_after(now + timedelta(days=730))
            .sign(self._csca_key, hashes.SHA256())                # signed with CSCA key
        )
        return dsc_key, dsc_cert

    def trusts(self, dsc_cert: x509.Certificate) -> bool:
        """Verify the DSC certificate is signed by our trusted CSCA."""
        try:
            self.csca_cert.public_key().verify(
                dsc_cert.signature, dsc_cert.tbs_certificate_bytes,
                _SIG,
            )
            return dsc_cert.issuer == self.csca_cert.subject
        except Exception:
            return False


# One station-level trust store for the process (built lazily).
_TRUST: Optional[TrustStore] = None


def get_truststore() -> TrustStore:
    global _TRUST
    if _TRUST is None:
        _TRUST = TrustStore()
    return _TRUST


@dataclass
class EMRTDChip:
    data_groups: dict[str, bytes]            # DG1 (MRZ), DG2 (face), DG15 (AA public key)
    sod_hashes: dict[str, str]               # signed at issuance
    sod_signature: bytes                     # DSC signature over the (canonical) sod_hashes
    dsc_cert_pem: bytes
    aa_private: Optional[ec.EllipticCurvePrivateKey] = None   # None on a CLONE
    aa_public_der: bytes = b""


def issue_chip(dg1: bytes, dg2: bytes, mode: str = "genuine",
               store: Optional[TrustStore] = None) -> EMRTDChip:
    """Synthesise an eMRTD chip and sign it with the trusted CSCA→DSC chain.
    mode: 'genuine' | 'tampered' (edit a DG after signing) | 'cloned' (no AA key)."""
    store = store or get_truststore()
    aa_key = ec.generate_private_key(_CURVE)
    aa_pub_der = aa_key.public_key().public_bytes(
        serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo)

    data_groups = {"DG1": dg1, "DG2": dg2, "DG15": aa_pub_der}
    sod_hashes = {dg: _sha256(b) for dg, b in data_groups.items()}   # hashes computed on ORIGINAL data

    dsc_key, dsc_cert = store.issue_dsc()
    sod_msg = json.dumps(sod_hashes, sort_keys=True).encode()
    sod_signature = dsc_key.sign(sod_msg, _SIG)

    chip = EMRTDChip(
        data_groups=dict(data_groups),
        sod_hashes=sod_hashes,
        sod_signature=sod_signature,
        dsc_cert_pem=dsc_cert.public_bytes(serialization.Encoding.PEM),
        aa_private=aa_key,
        aa_public_der=aa_pub_der,
    )

    if mode == "tampered":
        # Attacker edits a data group (e.g. DOB in DG1) AFTER the chip was signed.
        # The SOD hash no longer matches → PA fails. This is the flip-a-byte money-shot.
        original = chip.data_groups["DG1"]
        chip.data_groups["DG1"] = (b"X" + original[1:]) if original else b"X"
    elif mode == "cloned":
        # A clone copies all readable data but cannot copy the private AA key.
        chip.aa_private = None

    return chip


def passive_authentication(chip: EMRTDChip, store: Optional[TrustStore] = None) -> dict:
    """Verify DSC→CSCA chain + EF.SOD signature + recompute each data-group hash."""
    store = store or get_truststore()
    dsc_cert = x509.load_pem_x509_certificate(chip.dsc_cert_pem)

    chain_ok = store.trusts(dsc_cert)

    sod_msg = json.dumps(chip.sod_hashes, sort_keys=True).encode()
    try:
        dsc_cert.public_key().verify(chip.sod_signature, sod_msg, _SIG)
        sod_ok = True
    except Exception:
        sod_ok = False

    dg_hashes = {dg: (_sha256(b) == chip.sod_hashes.get(dg)) for dg, b in chip.data_groups.items()}
    result = "PASS" if (chain_ok and sod_ok and all(dg_hashes.values())) else "FAIL"
    return {"sod_signature": sod_ok, "dsc_to_csca_chain": chain_ok,
            "dg_hashes": dg_hashes, "result": result}


def active_authentication(chip: EMRTDChip) -> dict:
    """Challenge–response: only a genuine chip (holding the AA private key) can answer."""
    if chip.aa_private is None:
        return {"result": "FAIL", "detail": "chip cannot answer AA challenge (possible clone)"}
    challenge = os.urandom(16)
    try:
        signature = chip.aa_private.sign(challenge, _SIG)
        aa_pub = serialization.load_der_public_key(chip.data_groups["DG15"])
        aa_pub.verify(signature, challenge, _SIG)
        return {"result": "PASS"}
    except Exception:
        return {"result": "FAIL", "detail": "AA challenge verification failed"}
