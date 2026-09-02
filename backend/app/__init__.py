"""NEBULA — AI-Based Fake Identity & Document Screening System (backend).

Design principle (see Rough/research/06-BUILD-PLAN.md):
    The deterministic core (MRZ check-digits, validation rules, chip Passive-Auth,
    risk fusion, hash-chain ledger) DECIDES and cannot fail at runtime. Machine-learning
    modules (tamper, face, liveness, deepfake) only contribute weighted *signals* and
    always degrade to a fallback or `abstain` — never a crash, never the sole reason.
"""

__version__ = "0.1.0"
