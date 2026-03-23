from retrieval import hybrid_retrieve
from schemas import SearchRequest, SearchResponse


def _resolve_rerank(payload: SearchRequest) -> bool | None:
    return payload.rerank


async def search_documents(payload: SearchRequest) -> SearchResponse:
    hits, debug = hybrid_retrieve(payload, rerank=_resolve_rerank(payload))
    return SearchResponse(query=payload.query, hits=hits, debug=debug)
