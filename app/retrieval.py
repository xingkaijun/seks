import os
import re
import time
from typing import Any

from db import fetch_all
from embedding import get_embedding, vector_literal
from query_utils import apply_light_rerank
from schemas import SearchHit, SearchRequest


_TRUE_VALUES = {"1", "true", "yes", "on"}


def _bool_env(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None or str(raw).strip() == "":
        return default
    return str(raw).strip().lower() in _TRUE_VALUES


def _int_env(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or str(raw).strip() == "":
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _float_env(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None or str(raw).strip() == "":
        return default
    try:
        return float(raw)
    except ValueError:
        return default


_RETRIEVAL_TOPK_MAX = _int_env("RETRIEVAL_TOPK_MAX", 50)
_RETRIEVAL_CANDIDATE_MULTIPLIER = _int_env("RETRIEVAL_CANDIDATE_MULTIPLIER", 3)
_RETRIEVAL_KEYWORD_MAX_TERMS = _int_env("RETRIEVAL_KEYWORD_MAX_TERMS", 6)

_WEIGHT_FTS = _float_env("RETRIEVAL_WEIGHT_FTS", 1.0)
_WEIGHT_VECTOR = _float_env("RETRIEVAL_WEIGHT_VECTOR", 0.7)
_WEIGHT_KEYWORD = _float_env("RETRIEVAL_WEIGHT_KEYWORD", 0.6)

_RERANK_DEFAULT = _bool_env("RETRIEVAL_RERANK_ENABLED", True)

_TOKEN_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9\-_.]{1,}|[\u4e00-\u9fff]{2,}")
_STOPWORDS = {"what", "which", "with", "for", "the", "and", "are", "有哪些", "什么"}


def _build_filters(payload: SearchRequest) -> tuple[str, list]:
    clauses: list[str] = []
    params: list = []
    filters = payload.filters

    if not filters:
        return "", params

    scope_clauses: list[str] = []
    file_paths = getattr(filters, "file_paths", None)
    if file_paths:
        files = [p.strip() for p in file_paths if p and p.strip()]
        if files:
            scope_clauses.append("b.file_path = ANY(%s)")
            params.append(files)
    folder_paths = getattr(filters, "folder_paths", None)
    if folder_paths:
        folders = []
        for raw in folder_paths:
            if not raw or not raw.strip():
                continue
            cleaned = raw.strip()
            if cleaned == "/":
                folders.append("/")
            elif cleaned == ".":
                folders.append(".")
            else:
                folders.append(cleaned.rstrip("/"))
        patterns = []
        dot_only = False
        for folder in folders:
            if not folder:
                continue
            if folder == ".":
                dot_only = True
            elif folder == "/":
                patterns.append("/%")
            else:
                patterns.append(f"{folder}/%")
        if patterns:
            scope_clauses.append("b.file_path LIKE ANY(%s)")
            params.append(patterns)
        if dot_only:
            scope_clauses.append("b.file_path NOT LIKE %s")
            params.append("%/%")
    if scope_clauses:
        clauses.append("(" + " OR ".join(scope_clauses) + ")")

    if filters.title:
        clauses.append("b.title ILIKE %s")
        params.append(f"%{filters.title}%")
    if filters.chapter:
        clauses.append("c.chapter ILIKE %s")
        params.append(f"%{filters.chapter}%")
    if filters.page_start is not None:
        clauses.append("COALESCE(c.page_start, 0) >= %s")
        params.append(filters.page_start)
    if filters.page_end is not None:
        clauses.append("COALESCE(c.page_end, 999999) <= %s")
        params.append(filters.page_end)
    if filters.domain_tag:
        clauses.append("%s = ANY(COALESCE(b.domain_tags, ARRAY[]::text[]))")
        params.append(filters.domain_tag)

    if not clauses:
        return "", params
    return " AND " + " AND ".join(clauses), params


def _extract_keyword_terms(query: str) -> list[str]:
    terms: list[str] = []
    seen: set[str] = set()
    for match in _TOKEN_RE.finditer(query):
        token = match.group(0).strip()
        if not token:
            continue
        lowered = token.lower()
        if lowered in _STOPWORDS:
            continue
        if lowered in seen:
            continue
        seen.add(lowered)
        terms.append(token)
        if len(terms) >= _RETRIEVAL_KEYWORD_MAX_TERMS:
            break
    return terms


def _fts_hits(payload: SearchRequest, extra_where: str, extra_params: list, limit: int):
    sql = f"""
        SELECT
            c.id AS chunk_id,
            b.title AS book,
            c.chapter,
            c.page_start,
            c.page_end,
            c.chunk_text,
            ts_rank_cd(c.fts, websearch_to_tsquery('simple', %s)) AS score,
            'fts' AS source
        FROM chunks c
        JOIN books b ON b.id = c.book_id
        WHERE c.fts @@ websearch_to_tsquery('simple', %s)
        {extra_where}
        ORDER BY score DESC, c.id ASC
        LIMIT %s
    """
    params = [payload.query, payload.query, *extra_params, limit]
    return fetch_all(sql, tuple(params))


def _keyword_hits(
    terms: list[str],
    extra_where: str,
    extra_params: list,
    limit: int,
):
    if not terms:
        return []

    score_parts: list[str] = []
    where_parts: list[str] = []
    score_params: list[Any] = []
    where_params: list[Any] = []

    for term in terms:
        like = f"%{term}%"
        score_parts.append("CASE WHEN c.chunk_text ILIKE %s THEN 1 ELSE 0 END")
        score_parts.append("CASE WHEN b.title ILIKE %s THEN 0.6 ELSE 0 END")
        score_parts.append("CASE WHEN c.chapter ILIKE %s THEN 0.4 ELSE 0 END")
        score_params.extend([like, like, like])

        where_parts.append("(c.chunk_text ILIKE %s OR b.title ILIKE %s OR c.chapter ILIKE %s)")
        where_params.extend([like, like, like])

    score_parts.append("CASE WHEN c.keywords && %s::text[] THEN 1 ELSE 0 END")
    score_params.append([t.lower() for t in terms])
    where_parts.append("c.keywords && %s::text[]")
    where_params.append([t.lower() for t in terms])

    score_expr = " + ".join(score_parts) if score_parts else "0"
    where_expr = " OR ".join(where_parts) if where_parts else "TRUE"

    sql = f"""
        SELECT
            c.id AS chunk_id,
            b.title AS book,
            c.chapter,
            c.page_start,
            c.page_end,
            c.chunk_text,
            ({score_expr}) AS score,
            'keyword' AS source
        FROM chunks c
        JOIN books b ON b.id = c.book_id
        WHERE ({where_expr})
        {extra_where}
        ORDER BY score DESC, c.id ASC
        LIMIT %s
    """

    params = [*score_params, *where_params, *extra_params, limit]
    return fetch_all(sql, tuple(params))


def _vector_hits(payload: SearchRequest, extra_where: str, extra_params: list, limit: int):
    query_embedding = get_embedding(payload.query)
    sql = f"""
        SELECT
            c.id AS chunk_id,
            b.title AS book,
            c.chapter,
            c.page_start,
            c.page_end,
            c.chunk_text,
            (1 - (c.embedding <=> %s::vector)) AS score,
            'vector' AS source
        FROM chunks c
        JOIN books b ON b.id = c.book_id
        WHERE c.embedding IS NOT NULL
        {extra_where}
        ORDER BY c.embedding <=> %s::vector ASC, c.id ASC
        LIMIT %s
    """
    vector = vector_literal(query_embedding)
    params = [vector, *extra_params, vector, limit]
    return fetch_all(sql, tuple(params))


def _resolve_rerank(payload_flag: bool | None) -> bool:
    if payload_flag is None:
        return _RERANK_DEFAULT
    return bool(payload_flag)


def hybrid_retrieve(payload: SearchRequest, *, rerank: bool | None = None) -> tuple[list[SearchHit], dict[str, Any]]:
    started = time.perf_counter()
    query = (payload.query or "").strip()
    limit = max(1, min(payload.top_k, _RETRIEVAL_TOPK_MAX))
    candidate_k = max(limit, min(limit * _RETRIEVAL_CANDIDATE_MULTIPLIER, _RETRIEVAL_TOPK_MAX))

    debug: dict[str, Any] = {
        "query": query,
        "top_k": limit,
        "candidate_k": candidate_k,
        "signals": {"fts": 0, "keyword": 0, "vector": 0},
        "weights": {"fts": _WEIGHT_FTS, "keyword": _WEIGHT_KEYWORD, "vector": _WEIGHT_VECTOR},
        "keyword_terms": [],
        "rerank_enabled": False,
        "merged_candidates": 0,
        "hits_returned": 0,
    }

    if not query:
        debug["timing_ms"] = {"total": round((time.perf_counter() - started) * 1000, 2)}
        return [], debug

    extra_where, extra_params = _build_filters(payload)
    if payload.filters:
        debug["filters"] = payload.filters.model_dump(exclude_none=True)

    terms = _extract_keyword_terms(query)
    debug["keyword_terms"] = terms

    t0 = time.perf_counter()
    fts_rows = _fts_hits(payload, extra_where, extra_params, candidate_k)
    t1 = time.perf_counter()
    keyword_rows = _keyword_hits(terms, extra_where, extra_params, candidate_k)
    t2 = time.perf_counter()
    vector_rows = _vector_hits(payload, extra_where, extra_params, candidate_k)
    t3 = time.perf_counter()

    debug["signals"] = {"fts": len(fts_rows), "keyword": len(keyword_rows), "vector": len(vector_rows)}
    debug["timing_ms"] = {
        "fts": round((t1 - t0) * 1000, 2),
        "keyword": round((t2 - t1) * 1000, 2),
        "vector": round((t3 - t2) * 1000, 2),
    }

    merged: dict[int, dict[str, Any]] = {}

    def add_row(row: dict[str, Any], source: str, weight: float) -> None:
        chunk_id = row["chunk_id"]
        base_score = float(row.get("score") or 0.0)
        item = merged.get(chunk_id)
        if not item:
            item = {
                "chunk_id": chunk_id,
                "book": row["book"],
                "chapter": row.get("chapter"),
                "page_start": row.get("page_start"),
                "page_end": row.get("page_end"),
                "chunk_text": row["chunk_text"],
                "score_total": 0.0,
                "score_fts": 0.0,
                "score_keyword": 0.0,
                "score_vector": 0.0,
            }
            merged[chunk_id] = item
        item[f"score_{source}"] = max(item.get(f"score_{source}", 0.0), base_score)
        item["score_total"] += base_score * weight

    for row in fts_rows:
        add_row(row, "fts", _WEIGHT_FTS)
    for row in keyword_rows:
        add_row(row, "keyword", _WEIGHT_KEYWORD)
    for row in vector_rows:
        add_row(row, "vector", _WEIGHT_VECTOR)

    debug["merged_candidates"] = len(merged)

    ranked = sorted(merged.values(), key=lambda r: (r.get("score_total", 0.0), r["chunk_id"]), reverse=True)
    hits = [
        SearchHit(
            chunk_id=row["chunk_id"],
            book=row["book"],
            chapter=row.get("chapter"),
            page_start=row.get("page_start"),
            page_end=row.get("page_end"),
            chunk_text=row["chunk_text"],
            score=float(row.get("score_total", 0.0)),
        )
        for row in ranked[:limit]
    ]

    rerank_enabled = _resolve_rerank(rerank)
    debug["rerank_enabled"] = rerank_enabled
    if rerank_enabled and hits:
        base_scores = {hit.chunk_id: float(hit.score or 0.0) for hit in hits}
        hits = apply_light_rerank(query, hits)
        debug["rerank_top"] = [
            {
                "chunk_id": hit.chunk_id,
                "base_score": base_scores.get(hit.chunk_id, 0.0),
                "final_score": float(hit.score or 0.0),
                "delta": float(hit.score or 0.0) - base_scores.get(hit.chunk_id, 0.0),
            }
            for hit in hits[: min(5, len(hits))]
        ]

    debug["hits_returned"] = len(hits)
    debug["timing_ms"]["total"] = round((time.perf_counter() - started) * 1000, 2)

    return hits, debug
