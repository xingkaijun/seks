from typing import Any

from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    ok: bool = True
    service: str = "SEKS API"
    database: bool = True


class IngestRequest(BaseModel):
    file_path: str
    title: str
    author: str | None = None
    edition: str | None = None
    publish_year: int | None = None
    domain_tags: list[str] = Field(default_factory=list)


class IngestResponse(BaseModel):
    status: str
    message: str
    file_path: str
    title: str
    book_id: int
    chunk_count: int
    existing: bool = False


class SearchFilters(BaseModel):
    title: str | None = None
    chapter: str | None = None
    page_start: int | None = None
    page_end: int | None = None
    domain_tag: str | None = None
    folder_paths: list[str] | None = None
    file_paths: list[str] | None = None


class ScopeFileOption(BaseModel):
    book_id: int
    title: str
    file_path: str


class ScopeOptionsResponse(BaseModel):
    folders: list[str] = Field(default_factory=list)
    files: list[ScopeFileOption] = Field(default_factory=list)


class SearchRequest(BaseModel):
    query: str
    top_k: int = 10
    filters: SearchFilters | None = None
    rerank: bool | None = None


class AskRequest(BaseModel):
    question: str
    top_k: int = 8
    filters: SearchFilters | None = None
    rerank: bool | None = None
    llm_enabled: bool | None = None
    llm_model: str | None = None
    llm_temperature: float | None = None


class Citation(BaseModel):
    chunk_id: int
    book: str
    chapter: str | None = None
    page_start: int | None = None
    page_end: int | None = None


class SearchHit(BaseModel):
    chunk_id: int
    book: str
    chapter: str | None = None
    page_start: int | None = None
    page_end: int | None = None
    chunk_text: str
    score: float | None = None


class SearchResponse(BaseModel):
    query: str
    hits: list[SearchHit]
    debug: dict[str, Any] | None = None


class AskResponse(BaseModel):
    question: str
    answer: str
    citations: list[Citation]
    sources: list[SearchHit] = Field(default_factory=list)
    mode: str = "retrieval_only"
    debug: dict[str, Any] | None = None
