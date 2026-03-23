from datetime import datetime
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


class SearchRequest(BaseModel):
    query: str
    top_k: int = 10
    filters: SearchFilters | None = None


class AskRequest(BaseModel):
    question: str
    top_k: int = 8
    filters: SearchFilters | None = None
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


class AskResponse(BaseModel):
    question: str
    answer: str
    citations: list[Citation]
    sources: list[SearchHit] = Field(default_factory=list)
    mode: str = "retrieval_only"
    debug: dict[str, Any] | None = None


class BookListItem(BaseModel):
    id: int
    title: str
    file_path: str
    file_name: str
    folder: str
    chunk_count: int
    domain_tags: list[str] = Field(default_factory=list)
    page_count: int | None = None
    created_at: datetime | None = None


class BookListResponse(BaseModel):
    books: list[BookListItem]


class ChapterSummary(BaseModel):
    chapter: str | None = None
    section: str | None = None
    page_start: int | None = None
    page_end: int | None = None
    chunk_count: int = 0
    summary: str = ""


class BookDetailResponse(BaseModel):
    id: int
    title: str
    author: str | None = None
    edition: str | None = None
    publish_year: int | None = None
    domain_tags: list[str] = Field(default_factory=list)
    file_path: str
    file_name: str
    folder: str
    page_count: int | None = None
    chunk_count: int
    created_at: datetime | None = None
    chapters: list[ChapterSummary] = Field(default_factory=list)


class DeleteResponse(BaseModel):
    status: str = "ok"
    book_id: int
    title: str | None = None
