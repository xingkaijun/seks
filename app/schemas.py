from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, model_validator


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
    selected_book_ids: list[int] = Field(default_factory=list)
    file_paths: list[str] = Field(default_factory=list)
    folder_paths: list[str] = Field(default_factory=list)


class SearchRequest(BaseModel):
    query: str
    top_k: int = 10
    filters: SearchFilters | None = None
    rerank: bool | None = None

    @model_validator(mode="before")
    @classmethod
    def _accept_legacy_question_field(cls, data: Any):
        if isinstance(data, dict) and not data.get("query") and data.get("question"):
            data = dict(data)
            data["query"] = data["question"]
        return data


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
    chunk_text: str | None = None
    score: float | None = None


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


class ChapterSummary(BaseModel):
    chapter: str | None = None
    section: str | None = None
    page_start: int | None = None
    page_end: int | None = None
    chunk_count: int = 0
    summary: str | None = None


class BookSummary(BaseModel):
    id: int
    title: str
    author: str | None = None
    edition: str | None = None
    publish_year: int | None = None
    domain_tags: list[str] = Field(default_factory=list)
    file_path: str
    file_name: str | None = None
    folder: str | None = None
    page_count: int | None = None
    chunk_count: int = 0
    created_at: datetime | None = None


class BookDetail(BookSummary):
    chapters: list[ChapterSummary] = Field(default_factory=list)


class BookDetailResponse(BookDetail):
    pass


class BookListItem(BookSummary):
    pass


class BookListResponse(BaseModel):
    books: list[BookListItem] = Field(default_factory=list)
    total: int = 0
    items: list[BookSummary] = Field(default_factory=list)


class DeleteBookResponse(BaseModel):
    status: str
    book_id: int
    title: str | None = None
    chunk_count: int = 0


class DeleteResponse(DeleteBookResponse):
    pass


class ScopeFileOption(BaseModel):
    book_id: int
    title: str
    file_path: str


class ScopeOptionsResponse(BaseModel):
    folders: list[str] = Field(default_factory=list)
    files: list[ScopeFileOption] = Field(default_factory=list)


class SettingsResponse(BaseModel):
    llm_enabled: bool = False
    llm_base_url: str = ""
    llm_model: str = ""
    llm_api_key: str = ""
    llm_temperature: float = 0.2
    llm_timeout: float = 60.0
    embedding_provider: str = "local_sentence_transformers"
    embedding_model: str = ""
    access_password: str = ""


class SettingsUpdateRequest(BaseModel):
    llm_enabled: bool | None = None
    llm_base_url: str | None = None
    llm_model: str | None = None
    llm_api_key: str | None = None
    llm_temperature: float | None = None
    llm_timeout: float | None = None
    access_password: str | None = None
