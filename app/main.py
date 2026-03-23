from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from ask import ask_documents
from db import test_connection
from ingest import ingest_document
from library import delete_book, get_book_detail, list_books
from schemas import (
    AskRequest,
    AskResponse,
    BookDetailResponse,
    BookListResponse,
    DeleteResponse,
    HealthResponse,
    IngestRequest,
    IngestResponse,
    SearchRequest,
    SearchResponse,
)
from search import search_documents

app = FastAPI(title="SEKS API", version="0.2.0")

# Static UI (single-file). Keep it lightweight: no templates, no framework.
app.mount("/static", StaticFiles(directory="static"), name="static")


@app.get("/")
async def ui_index() -> FileResponse:
    return FileResponse("static/index.html")


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
async def books() -> BookListResponse:
    try:
        return list_books()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@app.get("/books/{book_id}", response_model=BookDetailResponse)
async def book_detail(book_id: int) -> BookDetailResponse:
    try:
        return get_book_detail(book_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@app.delete("/books/{book_id}", response_model=DeleteResponse)
async def book_delete(book_id: int) -> DeleteResponse:
    try:
        return delete_book(book_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e
