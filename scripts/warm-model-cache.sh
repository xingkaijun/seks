#!/usr/bin/env bash
set -euo pipefail

# Warm up the Hugging Face / sentence-transformers cache inside the running container.
# This is useful on slow networks: you can run it once after `docker compose up -d --build`
# so later ingests don't stall on first-time model download.
#
# Uses the configured EMBEDDING_MODEL / caching env vars from docker-compose + Dockerfile.

if ! command -v docker >/dev/null 2>&1; then
  echo "docker not found." >&2
  exit 1
fi

# Ensure service is up.
docker compose ps api >/dev/null 2>&1 || true

echo "Warming sentence-transformers model cache in container..."
docker compose exec -T api python - <<'PY'
import os
from sentence_transformers import SentenceTransformer

model = os.getenv("EMBEDDING_MODEL", "intfloat/multilingual-e5-small")
device = os.getenv("EMBEDDING_DEVICE", "cpu")
print(f"Loading model={model} device={device}")
SentenceTransformer(model, device=device)
print("OK: model cache warm")
PY
