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

## Deploy (Render free tier — ONNX, no GPU)
The stack is **onnxruntime-only** (no PyTorch/Paddle/binaries), so it deploys on Render's free
tier (512 MB, CPU):
- `backend/Dockerfile` builds a LITE image (`requirements-deploy.txt` + `rapidocr-onnxruntime --no-deps`).
- `render.yaml` (repo root) is a one-click blueprint (`/api/health` check, in-memory storage).
- **Image→MRZ works** via RapidOCR (ONNX): upload a document image → M1 reads + auto-corrects + validates.
- **Memory profile (512 MB):** the Dockerfile sets `LITE=1`, which **defers the tamper-CV stage** to
  free RAM for **OCR (runs in a memory-lean mode)**. Face (InsightFace) is excluded from the deploy
  requirements (M4 abstains). The deterministic core (~200 MB) is always reliable. **Caveat:** 512 MB is
  borderline for OCR — if image screening still OOMs (502), use a **≥2 GB** instance with `LITE=0`
  (full pipeline: OCR + tamper + face), or run image-upload demos locally.

Generate test images (no real documents):  `python -m tools.gen_mrz_image .`  → `mrz_valid.png`, `mrz_tampered.png`.
