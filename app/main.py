from pathlib import Path

from fastapi import FastAPI, HTTPException, Query, Response
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from ask import ask_documents
from db import test_connection
from ingest import ingest_document
from library import delete_book, get_book, list_books
from schemas import (
    AskRequest,
    AskResponse,
    BookDetail,
    BookListItem,
    BookListResponse,
    DeleteBookResponse,
    HealthResponse,
    IngestRequest,
    IngestResponse,
    SearchRequest,
    SearchResponse,
)
from search import search_documents

BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"
INDEX_HTML = STATIC_DIR / "index.html"

app = FastAPI(title="SEKS API", version="0.2.0")

# Static UI (single-file). Keep it lightweight: no templates, no framework.
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


@app.get("/")
async def ui_index() -> FileResponse:
    return FileResponse(str(INDEX_HTML))


@app.get("/library")
async def ui_library() -> FileResponse:
    return FileResponse(str(INDEX_HTML))


@app.get("/favicon.ico", include_in_schema=False)
async def favicon() -> Response:
    return Response(status_code=204)


@app.get("/healthz", response_model=HealthResponse)
async def healthz() -> HealthResponse:
    try:
        database_ok = test_connection()
    except Exception:
        database_ok = False
    return HealthResponse(ok=database_ok, database=database_ok)


@app.post("/ingest", response_model=IngestResponse)
async def ingest(payload: IngestRequest) -> IngestResponse:
    try:
        return await ingest_document(payload)
    except (FileNotFoundError, ValueError) as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@app.post("/search", response_model=SearchResponse)
async def search(payload: SearchRequest) -> SearchResponse:
    try:
        return await search_documents(payload)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@app.post("/ask", response_model=AskResponse)
async def ask(payload: AskRequest) -> AskResponse:
    try:
        return await ask_documents(payload)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@app.get("/books", response_model=BookListResponse)
async def books(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> BookListResponse:
    total, items = list_books(limit, offset)
    payload_items = [item.model_dump(mode="json") for item in items]
    return BookListResponse.model_validate({"total": total, "items": payload_items, "books": payload_items})


@app.get("/books/{book_id}", response_model=BookDetail)
async def book_detail(book_id: int) -> BookDetail:
    try:
        return get_book(book_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Book not found")


@app.delete("/books/{book_id}", response_model=DeleteBookResponse)
async def book_delete(book_id: int) -> DeleteBookResponse:
    deleted = delete_book(book_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Book not found")
    return DeleteBookResponse(status="deleted", **deleted)
