import os
import shutil
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query, Response, UploadFile, File, Form, Depends, Header, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from ask import ask_documents
from db import test_connection
from ingest import ingest_document_async, get_task_status
from library import delete_book, get_book, list_books, update_book
from library_fs import scan_library_tree
from schemas import (
    AskRequest,
    AskResponse,
    BookDetail,
    BookListResponse,
    BookUpdateRequest,
    DeleteBookResponse,
    HealthResponse,
    IngestRequest,
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
LIBRARY_DIR = Path(os.getenv("LIBRARY_DIR", "/data/library"))

ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "1102")

def verify_admin(x_admin_password: str = Header(None)):
    expected = ADMIN_PASSWORD
    if not expected:
        expected = load_settings().get("access_password") or "1102"
    if x_admin_password != expected:
        raise HTTPException(status_code=403, detail="管理员密码错误")


app = FastAPI(title="SEKS — Ship Engineering Knowledge System", version="0.3.0")

app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    if isinstance(exc, HTTPException):
        return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})
        
    user_msg = "服务内部异常，请联系管理员"
    status = 500
    detail = str(exc)

    if isinstance(exc, FileNotFoundError):
        user_msg = "找不到指定文件，请检查路径是否正确"
        status = 400
    elif isinstance(exc, ValueError):
        user_msg = f"参数错误: {detail[:100]}"
        status = 400
    elif "OperationalError" in type(exc).__name__:
        user_msg = "数据库连接异常，请稍后重试"
    elif "Embedding" in detail:
        user_msg = f"嵌入模型异常: {detail[:120]}"
    elif "LLM" in detail or "httpx" in detail.lower():
        user_msg = f"LLM 服务调用失败: {detail[:120]}"

    return JSONResponse(
        status_code=status,
        content={"user_message": user_msg, "detail": detail},
    )

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

@app.post("/upload")
async def upload_file(
    file: UploadFile = File(...),
    sub_path: str = Form(""),
    _=Depends(verify_admin)
):
    safe_sub = sub_path.replace("\\", "/").lstrip("/")
    if ".." in safe_sub:
        raise HTTPException(status_code=400, detail="非法路径")

    dest_dir = LIBRARY_DIR / safe_sub if safe_sub else LIBRARY_DIR
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest_file = dest_dir / file.filename

    with dest_file.open("wb") as f:
        shutil.copyfileobj(file.file, f)

    return {
        "status": "uploaded",
        "file_path": str(dest_file),
        "size": dest_file.stat().st_size,
    }


@app.post("/ingest")
async def ingest(payload: IngestRequest, _=Depends(verify_admin)):
    task_id = await ingest_document_async(payload)
    return {"status": "accepted", "task_id": task_id}

@app.get("/ingest/status/{task_id}")
async def ingest_status(task_id: str):
    task = get_task_status(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    return task


@app.post("/search", response_model=SearchResponse)
async def search(payload: SearchRequest) -> SearchResponse:
    return await search_documents(payload)

@app.post("/ask", response_model=AskResponse)
async def ask(payload: AskRequest) -> AskResponse:
    return await ask_documents(payload)

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

@app.patch("/books/{book_id}")
async def book_update(book_id: int, payload: BookUpdateRequest, _=Depends(verify_admin)):
    updates = payload.model_dump(exclude_unset=True)
    result = update_book(book_id, updates)
    if not result:
        raise HTTPException(status_code=404, detail="Book not found or no changes")
    return result


@app.delete("/books/{book_id}", response_model=DeleteBookResponse)
async def book_delete(book_id: int, _=Depends(verify_admin)) -> DeleteBookResponse:
    deleted = delete_book(book_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Book not found")
    return DeleteBookResponse(status="deleted", **deleted)


KEY_MAP_TO_STORE = {
    "llm_enabled": "enabled",
    "llm_base_url": "base_url",
    "llm_model": "model",
    "llm_api_key": "api_key",
    "llm_temperature": "temperature",
    "llm_timeout": "timeout",
}
KEY_MAP_FROM_STORE = {v: k for k, v in KEY_MAP_TO_STORE.items()}

@app.get("/api/settings", response_model=SettingsResponse)
async def get_settings_api() -> SettingsResponse:
    data = load_settings()
    resp = {}
    for k, v in data.items():
        if k in KEY_MAP_FROM_STORE:
            resp[KEY_MAP_FROM_STORE[k]] = v
        else:
            resp[k] = v

    if resp.get("llm_api_key"):
        if len(str(resp["llm_api_key"])) > 8:
            resp["llm_api_key"] = "****" + str(resp["llm_api_key"])[-4:]
        else:
            resp["llm_api_key"] = "****"
    if resp.get("access_password"):
        resp["access_password"] = "********"
    return SettingsResponse(**resp)


@app.put("/api/settings", response_model=SettingsResponse)
async def update_settings_api(payload: SettingsUpdateRequest) -> SettingsResponse:
    current = load_settings()
    updates = payload.model_dump(exclude_unset=True)

    mapped = {}
    for k, v in updates.items():
        mapped[KEY_MAP_TO_STORE.get(k, k)] = v
    updates = mapped

    if updates.get("api_key") and str(updates["api_key"]).startswith("****"):
        updates.pop("api_key", None)
    if updates.get("access_password") == "********":
        updates.pop("access_password", None)

    current.update(updates)
    saved = save_settings(current)

    resp = {}
    for k, v in saved.items():
        if k in KEY_MAP_FROM_STORE:
            resp[KEY_MAP_FROM_STORE[k]] = v
        else:
            resp[k] = v

    if resp.get("llm_api_key"):
        if len(str(resp["llm_api_key"])) > 8:
            resp["llm_api_key"] = "****" + str(resp["llm_api_key"])[-4:]
        else:
            resp["llm_api_key"] = "****"
    if resp.get("access_password"):
        resp["access_password"] = "********"
    return SettingsResponse(**resp)


@app.get("/api/scope-options", response_model=ScopeOptionsResponse)
async def get_scope_options_api() -> ScopeOptionsResponse:
    return list_scope_options()


@app.get("/api/library-tree")
async def library_tree():
    return {"tree": scan_library_tree()}


@app.get("/api/library-stats")
async def library_stats():
    from db import fetch_one
    row = fetch_one("""
        SELECT
            COUNT(DISTINCT b.id) AS book_count,
            COUNT(c.id) AS chunk_count,
            COALESCE(SUM(b.page_count), 0) AS total_pages
        FROM books b
        LEFT JOIN chunks c ON c.book_id = b.id
    """)
    return {
        "book_count": int(row.get("book_count", 0)) if row else 0,
        "chunk_count": int(row.get("chunk_count", 0)) if row else 0,
        "total_pages": int(row.get("total_pages", 0)) if row else 0,
    }
