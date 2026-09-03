# NEBULA screening backend — LITE (ONNX-only) image for Render free tier (512 MB, CPU).
FROM python:3.10-slim

# minimal system lib for opencv-python-headless
RUN apt-get update && apt-get install -y --no-install-recommends libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# install the lite deps, then rapidocr WITHOUT its deps (keeps opencv headless)
COPY requirements-deploy.txt .
RUN pip install --no-cache-dir -r requirements-deploy.txt \
    && pip install --no-cache-dir --no-deps rapidocr-onnxruntime==1.4.4

COPY app ./app

# Storage auto-detects: set MONGODB_URI in the environment to persist to MongoDB Atlas
# (survives Render free-tier spin-downs); otherwise it runs on the in-memory store.
ENV LLM_NARRATIVE=template \
    PYTHONUNBUFFERED=1 \
    OMP_NUM_THREADS=1 \
    OPENBLAS_NUM_THREADS=1 \
    WEB_CONCURRENCY=1

EXPOSE 8000
# Render provides $PORT
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
