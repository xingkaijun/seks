from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from ask import ask_documents
from db import test_connection
from ingest import ingest_document
from schemas import (
    AskRequest,
    AskResponse,
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
