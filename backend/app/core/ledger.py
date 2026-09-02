"""Tamper-evident audit ledger — hash-chain + Merkle root + signature.

REAL cryptography using only the Python standard library (hashlib/hmac). Each screening
record embeds the hash of the previous record, so altering any past record breaks every
subsequent hash (the demo "flip a record → chain breaks at the exact seq"). See
Rough/research/05-INTERNAL-DESIGN.md §6.

Note: HMAC-SHA256 is used as the record signature for the MVP. Production uses ed25519
keys held in an HSM/TPM — swap `_sign` accordingly.
"""
from __future__ import annotations

import hashlib
import hmac
import json
from datetime import datetime, timezone
from typing import Any, Optional

from ..models import Evidence

GENESIS = "0" * 64
# The exact fields covered by record_hash. verify() rebuilds `core` from these.
CORE_KEYS = ("seq", "session_id", "timestamp", "station_id",
             "doc_image_sha256", "evidence_digest", "verdict", "event")


def _canonical(obj: Any) -> str:
    # deterministic serialization (sorted keys, no whitespace) so hashing is stable.
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), default=str)


def _sha256(s: str) -> str:
    return hashlib.sha256(s.encode()).hexdigest()


def _sign(secret: str, msg: str) -> str:
    return hmac.new(secret.encode(), msg.encode(), hashlib.sha256).hexdigest()


def merkle_root(leaves: list[str]) -> str:
    """Standard binary Merkle root over the record hashes (duplicate last if odd)."""
    if not leaves:
        return _sha256("")
    layer = list(leaves)
    while len(layer) > 1:
        if len(layer) % 2 == 1:
            layer.append(layer[-1])
        layer = [_sha256(layer[i] + layer[i + 1]) for i in range(0, len(layer), 2)]
    return layer[0]


class Ledger:
    """Append-only ledger backed by a storage adapter (memory or mongo)."""

    def __init__(self, store, secret: str):
        self._store = store
        self._secret = secret

    def _seal(self, core: dict, prev_hash: str) -> dict:
        record_hash = _sha256(_canonical(core) + prev_hash)
        signature = _sign(self._secret, record_hash)
        return {**core, "prev_hash": prev_hash, "record_hash": record_hash, "signature": signature}

    async def _append_core(self, core_partial: dict) -> dict:
        prev = await self._store.ledger_last()
        seq = (prev["seq"] + 1) if prev else 0
        prev_hash = prev["record_hash"] if prev else GENESIS
        core = {
            "seq": seq,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "station_id": core_partial.get("station_id", ""),
            "session_id": core_partial.get("session_id"),
            "doc_image_sha256": core_partial.get("doc_image_sha256"),
            "evidence_digest": core_partial.get("evidence_digest"),
            "verdict": core_partial.get("verdict"),
            "event": core_partial.get("event", "SCREENING"),
        }
        record = self._seal(core, prev_hash)
        await self._store.ledger_append(record)
        return record

    async def append_screening(self, ev: Evidence) -> dict:
        evidence_digest = _sha256(_canonical(ev.model_dump(mode="json")))
        return await self._append_core({
            "station_id": ev.station_id,
            "session_id": ev.session_id,
            "doc_image_sha256": ev.context.doc_image_sha256,
            "evidence_digest": evidence_digest,
            "verdict": {"band": ev.fusion.band, "gate_fired": ev.fusion.gate_fired,
                        "risk": ev.fusion.risk},
            "event": "SCREENING",
        })

    async def append_decision(self, ev: Evidence, action: str) -> dict:
        # The officer's decision is a NEW linked record — the original verdict is never mutated.
        return await self._append_core({
            "station_id": ev.station_id,
            "session_id": ev.session_id,
            "doc_image_sha256": ev.context.doc_image_sha256,
            "evidence_digest": _sha256(_canonical({"officer_action": action})),
            "verdict": {"officer_action": action},
            "event": "OFFICER_DECISION",
        })

    async def verify(self) -> dict:
        """Recompute the whole chain: hashes, prev-links, signatures, Merkle root."""
        records = await self._store.ledger_all()
        prev_hash = GENESIS
        broken: list[int] = []
        for r in records:
            core = {k: r.get(k) for k in CORE_KEYS}
            expect = _sha256(_canonical(core) + prev_hash)
            link_ok = r.get("prev_hash") == prev_hash
            hash_ok = expect == r.get("record_hash")
            sig_ok = hmac.compare_digest(_sign(self._secret, r.get("record_hash", "")),
                                         r.get("signature", ""))
            if not (link_ok and hash_ok and sig_ok):
                broken.append(r.get("seq"))
            prev_hash = r.get("record_hash")
        return {
            "count": len(records),
            "intact": len(broken) == 0,
            "broken_seqs": broken,
            "merkle_root": merkle_root([r.get("record_hash", "") for r in records]),
        }

    async def all(self) -> list[dict]:
        return await self._store.ledger_all()

    async def demo_tamper(self, seq: int, band: Optional[str] = "LOW") -> dict:
        """DEMO ONLY: silently mutate a stored record's verdict WITHOUT re-hashing,
        so verify() detects the break at exactly this seq (the 'immutability you can see')."""
        await self._store.ledger_mutate(seq, {"verdict": {"band": band, "gate_fired": None,
                                                           "risk": 0.0, "_TAMPERED": True}})
        return await self.verify()
