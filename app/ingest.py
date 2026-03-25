import hashlib
from pathlib import Path

import asyncio
import uuid
from pypdf import PdfReader

from db import execute, execute_returning, fetch_one
from embedding import get_embedding_for_chunk, vector_literal
from schemas import IngestRequest, IngestResponse

_ingest_tasks: dict[str, dict] = {}

def get_task_status(task_id: str) -> dict | None:
    return _ingest_tasks.get(task_id)

def _extract_title_from_pdf(reader: PdfReader) -> str | None:
    try:
        meta = reader.metadata
        if meta and meta.title and meta.title.strip():
            return meta.title.strip()
    except:
        pass
    return None

def _extract_title_from_text(text: str) -> str | None:
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("#"):
            return stripped.lstrip("#").strip()
        return stripped[:100]
    return None


CHUNK_SIZE = 1000
OVERLAP = 120


def _file_hash(file_path: Path) -> str:
    h = hashlib.sha256()
    with file_path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _extract_text(file_path: Path) -> tuple[str, int | None]:
    suffix = file_path.suffix.lower()
    if suffix in {".txt", ".md"}:
        return file_path.read_text(encoding="utf-8", errors="ignore"), None
    if suffix == ".pdf":
        reader = PdfReader(str(file_path))
        pages = []
        for page in reader.pages:
            pages.append(page.extract_text() or "")
        return "\n\n".join(pages), len(reader.pages)
    raise ValueError(f"Unsupported file type: {suffix}")


def _split_text(text: str) -> list[str]:
    cleaned = "\n".join(line.rstrip() for line in text.splitlines())
    cleaned = cleaned.strip()
    if not cleaned:
        return []

    chunks: list[str] = []
    start = 0
    while start < len(cleaned):
        end = min(len(cleaned), start + CHUNK_SIZE)
        chunks.append(cleaned[start:end].strip())
        if end >= len(cleaned):
            break
        start = max(0, end - OVERLAP)
    return [c for c in chunks if c]


async def ingest_document_async(payload: IngestRequest) -> str:
    task_id = str(uuid.uuid4())[:8]
    _ingest_tasks[task_id] = {
        "status": "pending",
        "progress": 0,
        "total_chunks": 0,
        "file_path": payload.file_path,
        "title": payload.title,
        "book_id": None,
        "error": None,
    }
    asyncio.create_task(_run_ingest(task_id, payload))
    return task_id

async def _run_ingest(task_id: str, payload: IngestRequest):
    task = _ingest_tasks[task_id]
    try:
        task["status"] = "running"
        file_path = Path(payload.file_path).expanduser()
        if not file_path.exists() or not file_path.is_file():
            raise FileNotFoundError(f"File not found: {file_path}")

        file_hash = _file_hash(file_path)
        existing = fetch_one("SELECT id FROM books WHERE file_hash = %s", (file_hash,))

        text, page_count = _extract_text(file_path)
        chunks = _split_text(text)
        if not chunks:
            raise ValueError("No extractable text found in file")

        task["total_chunks"] = len(chunks)

        title = (payload.title or "").strip()
        if not title:
            suffix = file_path.suffix.lower()
            if suffix == ".pdf":
                try:
                    reader = PdfReader(str(file_path))
                    title = _extract_title_from_pdf(reader) or ""
                except:
                    pass
            if not title:
                title = _extract_title_from_text(text) or ""
            if not title:
                title = file_path.stem
        
        task["title"] = title

        if existing:
            book_id = existing["id"]
            execute("DELETE FROM chunks WHERE book_id = %s", (book_id,))
            execute(
                """
                UPDATE books
                SET title = %s,
                    author = %s,
                    edition = %s,
                    publish_year = %s,
                    domain_tags = %s,
                    file_path = %s,
                    page_count = %s
                WHERE id = %s
                """,
                (
                    title,
                    payload.author,
                    payload.edition,
                    payload.publish_year,
                    payload.domain_tags,
                    str(file_path),
                    page_count,
                    book_id,
                ),
            )
            existed = True
        else:
            row = execute_returning(
                """
                INSERT INTO books (title, author, edition, publish_year, domain_tags, file_path, file_hash, page_count)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id
                """,
                (
                    title,
                    payload.author,
                    payload.edition,
                    payload.publish_year,
                    payload.domain_tags,
                    str(file_path),
                    file_hash,
                    page_count,
                ),
            )
            if not row:
                raise RuntimeError("Failed to create book record")
            book_id = row["id"]
            existed = False

        task["book_id"] = book_id

        insert_sql = """
            INSERT INTO chunks (
                book_id, chapter, section, page_start, page_end, chunk_index, chunk_text, token_count, keywords, embedding
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s::vector)
        """

        for idx, chunk in enumerate(chunks):
            embedding = get_embedding_for_chunk(chunk)
            execute(
                insert_sql,
                (
                    book_id,
                    None,
                    None,
                    None,
                    None,
                    idx,
                    chunk,
                    max(1, len(chunk) // 4),
                    [],
                    vector_literal(embedding),
                ),
            )
            task["progress"] = idx + 1
            await asyncio.sleep(0)

        task["status"] = "done"
    except Exception as e:
        task["status"] = "error"
        task["error"] = str(e)

