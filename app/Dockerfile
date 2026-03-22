FROM python:3.12-slim

WORKDIR /app

# ---- Runtime + pip defaults for more reliable builds on slow/unstable networks ----
# - Avoid pip's self-update noise
# - Use longer default timeouts/retries during image build
# - Keep HF caches on the mounted /data/cache volume (see docker-compose.yml)
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_DEFAULT_TIMEOUT=120 \
    PIP_RETRIES=10 \
    HF_HUB_DISABLE_TELEMETRY=1 \
    HF_HUB_DISABLE_XET=1 \
    HF_HUB_DOWNLOAD_TIMEOUT=120 \
    HF_HUB_ETAG_TIMEOUT=120 \
    CACHE_DIR=/data/cache \
    SENTENCE_TRANSFORMERS_HOME=/data/cache/sentence-transformers \
    HF_HOME=/data/cache/hf

# torch (CPU) pulls a few native libs; install them explicitly to avoid surprises.
# (Most are already present, but this helps on minimal slim images.)
RUN apt-get update \
  && apt-get install -y --no-install-recommends \
       ca-certificates \
       curl \
       libgomp1 \
  && rm -rf /var/lib/apt/lists/*

COPY app/requirements.txt /app/requirements.txt
# Use --isolated to ignore host/global pip config (e.g. forced hash checking)
RUN python -m pip --isolated install --no-cache-dir -r /app/requirements.txt

COPY app /app

EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
