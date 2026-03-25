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
    ScopeOptionsResponse,
    SearchRequest,
    SearchResponse,
    SettingsResponse,
    SettingsUpdateRequest,
)
from scope import list_scope_options
from settings_store import load_settings, save_settings
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


@app.get("/settings")
async def ui_settings() -> FileResponse:
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


@app.get("/api/settings", response_model=SettingsResponse)
async def get_settings_api() -> SettingsResponse:
    data = load_settings()
    if data.get("api_key"):
        if len(str(data["api_key"])) > 8:
            data["api_key"] = "****" + str(data["api_key"])[-4:]
        else:
            data["api_key"] = "****"
    if data.get("access_password"):
        data["access_password"] = "********"
    return SettingsResponse(**data)


@app.put("/api/settings", response_model=SettingsResponse)
async def update_settings_api(payload: SettingsUpdateRequest) -> SettingsResponse:
    current = load_settings()
    updates = payload.model_dump(exclude_unset=True)
    if updates.get("api_key") and str(updates["api_key"]).startswith("****"):
        updates.pop("api_key", None)
    if updates.get("access_password") == "********":
        updates.pop("access_password", None)

    current.update(updates)
    saved = save_settings(current)

    if saved.get("api_key"):
        if len(str(saved["api_key"])) > 8:
            saved["api_key"] = "****" + str(saved["api_key"])[-4:]
        else:
            saved["api_key"] = "****"
    if saved.get("access_password"):
        saved["access_password"] = "********"
    return SettingsResponse(**saved)


@app.get("/api/scope-options", response_model=ScopeOptionsResponse)
async def get_scope_options_api() -> ScopeOptionsResponse:
    return list_scope_options()
