import hashlib
import json
import math
import os
import threading
import urllib.error
import urllib.request
from typing import Iterable

# Embedding providers:
# - local_sentence_transformers: local CPU embeddings via sentence-transformers (torch)
# - localhash: zero-dependency fallback (lower quality)
# - openai_compatible: call external OpenAI-compatible /embeddings endpoint
EMBEDDING_PROVIDER = os.getenv("EMBEDDING_PROVIDER", "local_sentence_transformers")

# OpenAI-compatible embeddings config
EMBEDDING_BASE_URL = os.getenv("EMBEDDING_BASE_URL", "")
# API key is optional for some gateways; we only send Authorization when non-empty.
EMBEDDING_API_KEY = os.getenv("EMBEDDING_API_KEY", "")

# Default model: 384d multilingual E5 small
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "intfloat/multilingual-e5-small")

# SEKS schema uses vector(384). Keep this fixed to avoid silent DB mismatches.
EMBEDDING_DIM = int(os.getenv("EMBEDDING_DIM", "384"))
if EMBEDDING_DIM != 384:
    raise RuntimeError(
        f"SEKS uses fixed 384-d embeddings (got EMBEDDING_DIM={EMBEDDING_DIM}). "
        "Update schema + re-ingest if you really need a different dimension."
    )

# Threading / performance knobs
EMBEDDING_THREADS = int(os.getenv("EMBEDDING_THREADS", "0"))
EMBEDDING_DEVICE = os.getenv("EMBEDDING_DEVICE", "cpu")

_LOCAL_MODEL = None
_LOCAL_MODEL_LOCK = threading.Lock()


def _normalize(vec: list[float]) -> list[float]:
    norm = math.sqrt(sum(v * v for v in vec))
    if norm == 0:
        return vec
    return [v / norm for v in vec]


def _tokenize(text: str) -> Iterable[str]:
    for token in text.lower().replace("\n", " ").split():
        t = token.strip()
        if t:
            yield t


def _localhash_embedding(text: str) -> list[float]:
    """Cheap local fallback embedding.

    NOTE: This is *not* semantic; it is a deterministic hashed bag-of-tokens.
    It exists only as a zero-dependency fallback.
    """

    vec = [0.0] * EMBEDDING_DIM
    tokens = list(_tokenize(text))
    if not tokens:
        return vec

    for token in tokens:
        digest = hashlib.sha256(token.encode("utf-8")).digest()
        idx = int.from_bytes(digest[:4], "big") % EMBEDDING_DIM
        sign = 1.0 if digest[4] % 2 == 0 else -1.0
        weight = 1.0 + (digest[5] / 255.0)
        vec[idx] += sign * weight

    for ch in text[:4000]:
        digest = hashlib.md5(ch.encode("utf-8")).digest()
        idx = int.from_bytes(digest[:4], "big") % EMBEDDING_DIM
        sign = 0.25 if digest[4] % 2 == 0 else -0.25
        vec[idx] += sign

    return _normalize(vec)


def _openai_compatible_embedding(text: str, *, is_query: bool) -> list[float]:
    """Call an OpenAI-compatible embeddings endpoint.

    Supports most OpenAI-compatible providers (OpenAI, Azure OpenAI via gateway,
    local LLM gateways, etc.). We keep this dependency-free by using urllib.

    Note: if you use an E5 model behind a gateway, it still expects
    `query:` / `passage:` prefixes; we apply them automatically.

    Env:
      - EMBEDDING_BASE_URL: e.g. https://api.example.com/v1
      - EMBEDDING_API_KEY: token (optional for some self-hosted gateways)
      - EMBEDDING_MODEL: model name
    """

    if not EMBEDDING_BASE_URL:
        raise RuntimeError("EMBEDDING_BASE_URL is missing")

    url = EMBEDDING_BASE_URL.rstrip("/") + "/embeddings"
    formatted = _format_e5_text(text, is_query=is_query)
    payload = json.dumps({"input": formatted, "model": EMBEDDING_MODEL}).encode("utf-8")

    headers = {"Content-Type": "application/json"}
    if EMBEDDING_API_KEY:
        headers["Authorization"] = f"Bearer {EMBEDDING_API_KEY}"

    req = urllib.request.Request(url, data=payload, headers=headers, method="POST")

    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:  # pragma: no cover
        body = ""
        try:
            body = e.read().decode("utf-8", errors="ignore")
        except Exception:
            body = ""
        raise RuntimeError(f"Embedding API HTTP {e.code}: {body or e.reason}") from e
    except urllib.error.URLError as e:  # pragma: no cover
        raise RuntimeError(f"Embedding API connection error: {e}") from e

    try:
        embedding = data["data"][0]["embedding"]
    except Exception as e:
        raise RuntimeError(f"Invalid embedding response: {data}") from e

    if not isinstance(embedding, list):
        raise RuntimeError("Invalid embedding response format")
    if len(embedding) != EMBEDDING_DIM:
        raise RuntimeError(
            f"Embedding dimension mismatch: API returned {len(embedding)} dims, expected {EMBEDDING_DIM}. "
            "Update model/dim + DB schema and re-ingest if needed."
        )
    # Ensure cosine-friendly vectors (pgvector vector_cosine_ops).
    return _normalize([float(x) for x in embedding])


def _get_sentence_transformers_model():
    """Lazy init sentence-transformers model.

    This is heavier than fastembed/onnx (requires torch), but yields better quality.
    Models are downloaded from Hugging Face into a cache dir.
    """

    global _LOCAL_MODEL
    if _LOCAL_MODEL is not None:
        return _LOCAL_MODEL

    with _LOCAL_MODEL_LOCK:
        if _LOCAL_MODEL is not None:
            return _LOCAL_MODEL

        # HuggingFace Hub defaults can look like a "hang" on slower/unstable links.
        os.environ.setdefault("HF_HUB_DISABLE_TELEMETRY", "1")
        os.environ.setdefault("HF_HUB_DISABLE_XET", "1")
        os.environ.setdefault("HF_HUB_DOWNLOAD_TIMEOUT", "60")
        os.environ.setdefault("HF_HUB_ETAG_TIMEOUT", "60")
        # Optional: users can set HF_ENDPOINT in .env for mirrors (e.g. in CN networks).

        # Cache directory strategy:
        # - In docker-compose we set CACHE_DIR=/data/cache (mounted volume).
        # - For local dev runs outside containers, default to ~/.cache/seks.
        cache_root = (
            os.getenv("SENTENCE_TRANSFORMERS_HOME")
            or os.getenv("CACHE_DIR")
            or os.getenv("XDG_CACHE_HOME")
            or os.path.join(os.path.expanduser("~"), ".cache", "seks")
        )
        cache_root = os.path.expanduser(cache_root)
        cache_dir = (
            cache_root
            if cache_root.endswith("/sentence-transformers")
            else os.path.join(cache_root, "sentence-transformers")
        )
        os.makedirs(cache_dir, exist_ok=True)
        os.environ.setdefault("SENTENCE_TRANSFORMERS_HOME", cache_dir)

        # Keep HF_HOME inside the same cache root as well.
        if not os.getenv("HF_HOME"):
            os.environ.setdefault("HF_HOME", os.path.join(os.path.dirname(cache_dir), "hf"))

        try:
            # Torch is imported inside sentence-transformers; import torch early to set threads.
            import torch

            if EMBEDDING_THREADS and EMBEDDING_THREADS > 0:
                torch.set_num_threads(EMBEDDING_THREADS)
                # Interop threads can hurt on small CPUs; keep conservative.
                torch.set_num_interop_threads(max(1, min(EMBEDDING_THREADS, 4)))

            from sentence_transformers import SentenceTransformer
        except Exception as e:  # pragma: no cover
            raise RuntimeError(
                "sentence-transformers is not installed. Install requirements.txt or set EMBEDDING_PROVIDER=localhash"
            ) from e

        _LOCAL_MODEL = SentenceTransformer(
            EMBEDDING_MODEL,
            device=EMBEDDING_DEVICE,
            cache_folder=cache_dir,
        )
        return _LOCAL_MODEL


def _format_e5_text(text: str, *, is_query: bool) -> str:
    # E5 family expects explicit prefixes.
    # See: https://huggingface.co/intfloat/multilingual-e5-small
    if "e5" in EMBEDDING_MODEL.lower():
        prefix = "query: " if is_query else "passage: "
        return prefix + text
    return text


def _local_sentence_transformers_embedding(text: str, *, is_query: bool) -> list[float]:
    model = _get_sentence_transformers_model()
    formatted = _format_e5_text(text, is_query=is_query)

    # normalize_embeddings=True is recommended for cosine similarity (pgvector vector_cosine_ops)
    vec = model.encode(
        [formatted],
        normalize_embeddings=True,
        show_progress_bar=False,
        batch_size=1,
    )[0]

    out = [float(x) for x in vec.tolist()]
    if len(out) != EMBEDDING_DIM:
        raise RuntimeError(
            f"Embedding dimension mismatch: model returned {len(out)} dims, expected {EMBEDDING_DIM}. "
            "Update model/dim + DB schema and re-ingest if needed."
        )
    return out


def get_embedding(text: str) -> list[float]:
    """Get a vector for a query text.

    For document chunk embeddings during ingest, prefer get_embedding_for_chunk().
    """

    provider = EMBEDDING_PROVIDER.lower()
    if provider == "localhash":
        return _localhash_embedding(text)
    if provider in {
        "local_sentence_transformers",
        "local-sentence-transformers",
        "sentence_transformers",
        "sentence-transformers",
        "st",
    }:
        return _local_sentence_transformers_embedding(text, is_query=True)
    if provider in {"openai_compatible", "openai-compatible", "openai"}:
        return _openai_compatible_embedding(text, is_query=True)
    raise RuntimeError(f"Unsupported embedding provider: {EMBEDDING_PROVIDER}")


def get_embedding_for_chunk(text: str) -> list[float]:
    """Get a vector for a document passage/chunk."""

    provider = EMBEDDING_PROVIDER.lower()
    if provider == "localhash":
        return _localhash_embedding(text)
    if provider in {
        "local_sentence_transformers",
        "local-sentence-transformers",
        "sentence_transformers",
        "sentence-transformers",
        "st",
    }:
        return _local_sentence_transformers_embedding(text, is_query=False)
    if provider in {"openai_compatible", "openai-compatible", "openai"}:
        return _openai_compatible_embedding(text, is_query=False)
    raise RuntimeError(f"Unsupported embedding provider: {EMBEDDING_PROVIDER}")


def vector_literal(vec: list[float]) -> str:
    return "[" + ",".join(f"{v:.8f}" for v in vec) + "]"
