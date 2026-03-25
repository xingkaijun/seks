from __future__ import annotations

from db import execute_returning, fetch_all, fetch_one
from schemas import (
    BookDetail,
    BookListResponse,
    BookSummary,
    ChapterSummary,
    DeleteBookResponse,
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


def list_books(limit: int = 50, offset: int = 0) -> tuple[int, list[BookSummary]]:
    total_row = fetch_one("SELECT COUNT(*) AS total FROM books") or {"total": 0}
    rows = fetch_all(
        """
        SELECT
            b.id,
            b.title,
            b.author,
            b.edition,
            b.publish_year,
            b.file_path,
            b.domain_tags,
            b.page_count,
            b.created_at,
            COUNT(c.id) AS chunk_count
        FROM books b
        LEFT JOIN chunks c ON c.book_id = b.id
        GROUP BY b.id
        ORDER BY b.created_at DESC NULLS LAST, b.id DESC
        LIMIT %s OFFSET %s
        """,
        (limit, offset),
    )

    items: list[BookSummary] = []
    for row in rows:
        file_name, folder = _split_path(row.get("file_path") or "")
        items.append(
            BookSummary(
                id=row["id"],
                title=row.get("title") or "",
                author=row.get("author"),
                edition=row.get("edition"),
                publish_year=row.get("publish_year"),
                file_path=row.get("file_path") or "",
                file_name=file_name,
                folder=folder,
                chunk_count=int(row.get("chunk_count") or 0),
                domain_tags=row.get("domain_tags") or [],
                page_count=row.get("page_count"),
                created_at=row.get("created_at"),
            )
        )

    return int(total_row.get("total") or 0), items


def get_book(book_id: int) -> BookDetail:
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

    return BookDetail(
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


def delete_book(book_id: int) -> dict | None:
    count_row = fetch_one("SELECT COUNT(*) AS chunk_count, MAX(title) AS title FROM chunks c JOIN books b ON b.id = c.book_id WHERE b.id = %s", (book_id,))
    row = execute_returning(
        """
        DELETE FROM books
        WHERE id = %s
        RETURNING id, title
        """,
        (book_id,),
    )
    if not row:
        return None

    return {
        "book_id": row["id"],
        "title": row.get("title") or count_row.get("title") if count_row else row.get("title"),
        "chunk_count": int((count_row or {}).get("chunk_count") or 0),
    }

def update_book(book_id: int, updates: dict) -> dict | None:
    sets = []
    params = []
    if "title" in updates and updates["title"] is not None:
        sets.append("title = %s")
        params.append(updates["title"])
    if "edition" in updates and updates["edition"] is not None:
        sets.append("edition = %s")
        params.append(updates["edition"])
    if "domain_tags" in updates and updates["domain_tags"] is not None:
        sets.append("domain_tags = %s")
        params.append(updates["domain_tags"])
    if not sets:
        return None
    params.append(book_id)
    sql = f"UPDATE books SET {', '.join(sets)} WHERE id = %s RETURNING id, title, edition, domain_tags"
    return execute_returning(sql, tuple(params))

