# NEBULA — Backend (Screening API)

AI-Based Fake Identity & Document Screening System · SIH 2026 · PS 26188 · Team NEBULA.

**Design principle:** the deterministic core (MRZ check digits, validation rules, risk
fusion, hash-chain audit ledger) *decides* and cannot fail at runtime; ML modules
(tamper, face, chip) only add weighted *signals* and always degrade to a fallback.
Full plan: `../Rough/research/06-BUILD-PLAN.md` and `05-INTERNAL-DESIGN.md`.

## What's REAL right now (Week 1 spine)
- **Module 1 (OCR/MRZ):** real MRZ-*text* parse + ICAO 9303 check digits (offline, no deps).
  Image OCR path is a labelled stub (needs Tesseract — Week 2).
- **Module 2 (Validation):** real rules — check digits, dates, country codes, MRZ↔printed cross-check.
- **Risk fusion:** real — hard-rule gates + calibrated weighted score + bands + abstain.
- **Audit ledger:** real — hash-chain + Merkle root + HMAC signature + verify + tamper demo.
- **Modules 3/4/5 (tamper/face/chip):** labelled **STUB** — contribute no signal (nothing faked).

## Run it (Windows, Python 3.10)
```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python -m pytest            # run the core tests
python run.py              # start the API on http://127.0.0.1:8000
```
Open http://127.0.0.1:8000 for the minimal (no-CSS) console.

## Storage
Runs on an in-memory store by default (no setup). To use MongoDB, set in `.env`:
```
STORAGE_BACKEND=mongo
MONGO_URI=mongodb://localhost:27017
```

## Key endpoints
- `GET /api/selftest` — deterministic-core readiness board.
- `GET /api/sample?variant=valid|tampered` — legal synthetic passport MRZ.
- `POST /api/screen` — run a screening (paste MRZ and/or upload a document).
- `GET /api/ledger/verify` — recompute chain integrity + Merkle root.
- `POST /api/ledger/tamper-demo` — mutate a record so the chain visibly breaks.

## Config / secrets
Copy `.env.example` to `.env`. The backend runs with safe defaults if you don't.
