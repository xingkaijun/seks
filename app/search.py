from db import fetch_all
from embedding import get_embedding, vector_literal
from schemas import SearchHit, SearchRequest, SearchResponse


def _build_filters(payload: SearchRequest) -> tuple[str, list]:
    clauses: list[str] = []
    params: list = []
    filters = payload.filters

    if not filters:
        return "", params

    scope_clauses: list[str] = []
    if filters.file_paths:
        files = [p.strip() for p in filters.file_paths if p and p.strip()]
        if files:
            scope_clauses.append("b.file_path = ANY(%s)")
            params.append(files)
    if filters.folder_paths:
        folders = []
        for raw in filters.folder_paths:
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


async def search_documents(payload: SearchRequest) -> SearchResponse:
    limit = max(1, min(payload.top_k, 50))
    extra_where, extra_params = _build_filters(payload)

    merged: dict[int, dict] = {}

    for row in _fts_hits(payload, extra_where, extra_params, limit):
        row["score"] = float(row.get("score") or 0.0)
        row["score_total"] = row["score"] * 1.0
        merged[row["chunk_id"]] = row

    for row in _vector_hits(payload, extra_where, extra_params, limit):
        row["score"] = float(row.get("score") or 0.0)
        if row["chunk_id"] in merged:
            merged[row["chunk_id"]]["score_total"] += row["score"] * 0.7
        else:
            row["score_total"] = row["score"] * 0.7
            merged[row["chunk_id"]] = row

    ranked = sorted(merged.values(), key=lambda r: (r.get("score_total", 0.0), r["chunk_id"]), reverse=True)
    hits = [
        SearchHit(
            chunk_id=row["chunk_id"],
            book=row["book"],
            chapter=row.get("chapter"),
            page_start=row.get("page_start"),
            page_end=row.get("page_end"),
            chunk_text=row["chunk_text"],
            score=float(row.get("score_total", row.get("score", 0.0))),
        )
        for row in ranked[:limit]
    ]

    return SearchResponse(query=payload.query, hits=hits)
