import os
import re

from llm import generate_rag_answer, llm_settings
from query_utils import apply_light_rerank, expand_question_queries, is_noisy_chunk, keyword_terms
from retrieval import hybrid_retrieve
from schemas import AskRequest, AskResponse, Citation, SearchRequest


_TRUE_VALUES = {"1", "true", "yes", "on"}
_SENTENCE_SPLIT_RE = re.compile(r"(?<=[。！？.!?])\s+|\n+")


def _bool_env(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None or str(raw).strip() == "":
        return default
    return str(raw).strip().lower() in _TRUE_VALUES


def _default_ask_rerank() -> bool:
    if os.getenv("ASK_RERANK_ENABLED") is None:
        return _bool_env("RETRIEVAL_RERANK_ENABLED", True)
    return _bool_env("ASK_RERANK_ENABLED", True)


def _resolve_rerank(payload_flag: bool | None) -> bool:
    if payload_flag is None:
        return _default_ask_rerank()
    return bool(payload_flag)


def _extract_relevant_excerpt(text: str, keywords: set[str]) -> str:
    """从文本中提取与关键词最相关的片段。"""
    cleaned = text.strip().replace("\r", "")
    parts = [p.strip() for p in _SENTENCE_SPLIT_RE.split(cleaned) if p.strip()]
    if not parts:
        return cleaned[:240] + ("…" if len(cleaned) > 240 else "")

    scored: list[tuple[int, str]] = []
    for part in parts:
        lowered = part.lower()
        score = 0
        for kw in keywords:
            if kw in lowered or kw in part:
                score += 2
        if is_noisy_chunk(part):
            score -= 3
        scored.append((score, part))

    scored.sort(key=lambda x: (x[0], len(x[1])), reverse=True)
    best = scored[0][1]
    return best[:260] + ("…" if len(best) > 260 else "")


def _dedupe_hits(hits):
    seen: set[int] = set()
    out = []
    for hit in hits:
        if hit.chunk_id in seen:
            continue
        seen.add(hit.chunk_id)
        out.append(hit)
    return out


def _fallback_summary(question: str, hits) -> str:
    """基于检索结果生成通用摘要回答。"""
    if not hits:
        return "当前知识库里没有检索到足够证据，暂时不能可靠回答这个问题。"

    keywords = keyword_terms(question)
    useful_hits = [hit for hit in hits if not is_noisy_chunk(hit.chunk_text)]
    if not useful_hits:
        useful_hits = hits[:3]

    lines = [f"问题：{question}", "基于当前命中的资料，先给出可追溯的整理："]
    for idx, hit in enumerate(useful_hits[:5], start=1):
        excerpt = _extract_relevant_excerpt(hit.chunk_text, keywords)
        loc = []
        if hit.chapter:
            loc.append(hit.chapter)
        if hit.page_start is not None or hit.page_end is not None:
            loc.append(f"页码 {hit.page_start}-{hit.page_end}")
        loc_text = f"（{'，'.join(loc)}）" if loc else ""
        lines.append(f"证据 {idx}. 《{hit.book}》{loc_text}：{excerpt}")

    lines.append("以上内容为基于检索结果的整理；当前仍是 retrieval-only 回答，已尽量过滤噪声并保留可追溯证据。")
    return "\n".join(lines)


def _build_contexts(hits):
    return [
        {
            "chunk_id": hit.chunk_id,
            "book": hit.book,
            "chapter": hit.chapter,
            "page_start": hit.page_start,
            "page_end": hit.page_end,
            "chunk_text": hit.chunk_text,
            "score": hit.score,
        }
        for hit in hits
    ]


async def ask_documents(payload: AskRequest) -> AskResponse:
    merged_hits = []
    retrieval_debug: list[dict] = []
    queries = expand_question_queries(payload.question)
    candidate_k = max(payload.top_k, 8)
    for query in queries:
        hits, debug = await hybrid_retrieve(
            SearchRequest(query=query, top_k=candidate_k, filters=payload.filters),
            rerank=False,
        )
        merged_hits.extend(hits)
        retrieval_debug.append(
            {
                "query": debug.get("query", query),
                "signals": debug.get("signals"),
                "merged_candidates": debug.get("merged_candidates"),
                "hits_returned": debug.get("hits_returned"),
                "keyword_terms": debug.get("keyword_terms"),
                "timing_ms": debug.get("timing_ms"),
            }
        )

    deduped_hits = _dedupe_hits(merged_hits)
    ask_rerank_enabled = _resolve_rerank(payload.rerank)
    rerank_debug: list[dict] = []
    if ask_rerank_enabled:
        ranked_hits, rerank_debug = apply_light_rerank(payload.question, deduped_hits, return_debug=True)
    else:
        ranked_hits = deduped_hits
    top_hits = ranked_hits[: payload.top_k]

    citations = [
        Citation(
            chunk_id=hit.chunk_id,
            book=hit.book,
            chapter=hit.chapter,
            page_start=hit.page_start,
            page_end=hit.page_end,
            chunk_text=hit.chunk_text,
            score=hit.score,
        )
        for hit in top_hits[: min(len(top_hits), 8)]
    ]

    contexts = _build_contexts(top_hits)
    mode = "retrieval_only"
    debug: dict = {
        "retrieved_hits": len(top_hits),
        "queries": queries,
        "rerank_enabled": ask_rerank_enabled,
        "retrieval": {
            "per_query": retrieval_debug,
            "merged_candidates": len(merged_hits),
            "deduped_candidates": len(deduped_hits),
            "top_k": payload.top_k,
        },
    }
    if rerank_debug:
        debug["rerank_top"] = rerank_debug[: min(5, len(rerank_debug))]

    llm_overrides = {
        "enabled": payload.llm_enabled,
        "model": payload.llm_model,
        "temperature": payload.llm_temperature,
    }

    answer = ""
    llm_error = None
    settings = llm_settings(llm_overrides)
    if settings["enabled"] and top_hits:
        try:
            answer = await generate_rag_answer(question=payload.question, contexts=contexts, overrides=llm_overrides)
            mode = "llm_rag"
        except Exception as exc:
            llm_error = str(exc)

    if not answer:
        answer = _fallback_summary(payload.question, top_hits)

    debug["mode"] = mode
    if llm_error:
        debug["llm_error"] = llm_error
    if settings["base_url"]:
        debug["llm_base_url"] = settings["base_url"]
    if settings["model"]:
        debug["llm_model"] = settings["model"]

    return AskResponse(
        question=payload.question,
        answer=answer,
        citations=citations,
        sources=top_hits,
        mode=mode,
        debug=debug,
    )
