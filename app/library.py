from __future__ import annotations

from db import execute_returning, fetch_all, fetch_one
from schemas import (
    BookDetailResponse,
    BookListItem,
    BookListResponse,
    ChapterSummary,
    DeleteResponse,
)


SUMMARY_LIMIT = 160


def _split_path(file_path: str) -> tuple[str, str]:
    cleaned = (file_path or "").strip()
    if not cleaned:
        return "", ""
    normalized = cleaned.replace("\\", "/").rstrip("/")
    if "/" not in normalized:
        return normalized, ""
    folder, name = normalized.rsplit("/", 1)
    return name, folder


def _summarize(text: str | None, limit: int = SUMMARY_LIMIT) -> str:
    if not text:
        return ""
    compact = " ".join(text.split())
    if len(compact) <= limit:
        return compact
    return compact[:limit].rstrip() + "..."


def list_books() -> BookListResponse:
    rows = fetch_all(
        """
        SELECT
            b.id,
            b.title,
            b.file_path,
            b.domain_tags,
            b.page_count,
            b.created_at,
            COUNT(c.id) AS chunk_count
        FROM books b
        LEFT JOIN chunks c ON c.book_id = b.id
        GROUP BY b.id
        ORDER BY b.created_at DESC, b.id DESC
        """
    )

    items: list[BookListItem] = []
    for row in rows:
        file_name, folder = _split_path(row.get("file_path") or "")
        items.append(
            BookListItem(
                id=row["id"],
                title=row.get("title") or "",
                file_path=row.get("file_path") or "",
                file_name=file_name,
                folder=folder,
                chunk_count=int(row.get("chunk_count") or 0),
                domain_tags=row.get("domain_tags") or [],
                page_count=row.get("page_count"),
                created_at=row.get("created_at"),
            )
        )

    return BookListResponse(books=items)


def get_book_detail(book_id: int) -> BookDetailResponse:
    row = fetch_one(
        """
        SELECT
            b.id,
            b.title,
            b.author,
            b.edition,
            b.publish_year,
            b.domain_tags,
            b.file_path,
            b.page_count,
            b.created_at,
            COUNT(c.id) AS chunk_count
        FROM books b
        LEFT JOIN chunks c ON c.book_id = b.id
        WHERE b.id = %s
        GROUP BY b.id
        """,
        (book_id,),
    )
    if not row:
        raise ValueError(f"Book not found: {book_id}")

    file_name, folder = _split_path(row.get("file_path") or "")

    chapter_rows = fetch_all(
        """
        SELECT DISTINCT ON (chapter, section)
            chapter,
            section,
            COUNT(*) OVER (PARTITION BY chapter, section) AS chunk_count,
            MIN(page_start) OVER (PARTITION BY chapter, section) AS page_start,
            MAX(page_end) OVER (PARTITION BY chapter, section) AS page_end,
            chunk_text
        FROM chunks
        WHERE book_id = %s
        ORDER BY chapter NULLS FIRST, section NULLS FIRST, chunk_index ASC, id ASC
        """,
        (book_id,),
    )

    chapters: list[ChapterSummary] = []
    for c in chapter_rows:
        chapters.append(
            ChapterSummary(
                chapter=c.get("chapter"),
                section=c.get("section"),
                page_start=c.get("page_start"),
                page_end=c.get("page_end"),
                chunk_count=int(c.get("chunk_count") or 0),
                summary=_summarize(c.get("chunk_text")),
            )
        )

    return BookDetailResponse(
        id=row["id"],
        title=row.get("title") or "",
        author=row.get("author"),
        edition=row.get("edition"),
        publish_year=row.get("publish_year"),
        domain_tags=row.get("domain_tags") or [],
        file_path=row.get("file_path") or "",
        file_name=file_name,
        folder=folder,
        page_count=row.get("page_count"),
        chunk_count=int(row.get("chunk_count") or 0),
        created_at=row.get("created_at"),
        chapters=chapters,
    )


def delete_book(book_id: int) -> DeleteResponse:
    row = execute_returning(
        """
        DELETE FROM books
        WHERE id = %s
        RETURNING id, title
        """,
        (book_id,),
    )
    if not row:
        raise ValueError(f"Book not found: {book_id}")

    return DeleteResponse(status="ok", book_id=row["id"], title=row.get("title"))
