"""
FastAPI application for the Clinical Co-Pilot service.

Endpoints:
  POST /chat          — main agent endpoint, returns SSE stream
  POST /clear         — clear conversation history for a session
  GET  /health        — health check
  GET  /logs          — tail recent observability log entries (last N lines)

All endpoints except /health require the X-Copilot-Secret header to match
the configured COPILOT_SECRET. This prevents unauthenticated access from
outside the Docker network.

The service is NOT exposed on a public port — it runs on 0.0.0.0:8400
inside the Docker network only, accessible via the OpenEMR Apache proxy.
"""
import json
import os
import tempfile
from pathlib import Path
from typing import AsyncGenerator

from fastapi import FastAPI, File, Form, Header, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from agent import chat, clear_conversation, get_conversation_length
from config import COPILOT_SECRET, DEMO_MODE, LOG_FILE
from graph import run_graph
from ingest import attach_and_extract

app = FastAPI(
    title="Clinical Co-Pilot",
    description="AI agent embedded in OpenEMR for primary care physicians",
    version="1.0.0",
)

# Allow requests from the OpenEMR container (same Docker network)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Restricted by Docker network topology, not CORS
    allow_methods=["*"],
    allow_headers=["*"],
)


def _require_auth(secret: str | None):
    if secret != COPILOT_SECRET:
        raise HTTPException(status_code=401, detail="Unauthorized")


class ChatRequest(BaseModel):
    session_id: str
    pid: int
    question: str


class ClearRequest(BaseModel):
    session_id: str


class V2QueryRequest(BaseModel):
    session_id: str
    pid: int
    query: str
    file_path: str | None = None
    doc_type: str | None = None  # "lab_pdf" | "intake_form"


@app.get("/health")
def health():
    return {
        "status": "ok",
        "demo_mode": DEMO_MODE,
        "service": "clinical-copilot",
    }


@app.post("/chat")
async def chat_endpoint(
    req: ChatRequest,
    x_copilot_secret: str | None = Header(default=None),
):
    _require_auth(x_copilot_secret)

    if not req.question.strip():
        raise HTTPException(status_code=400, detail="Question cannot be empty")

    if req.pid <= 0:
        raise HTTPException(status_code=400, detail="Invalid patient ID")

    async def event_stream() -> AsyncGenerator[bytes, None]:
        async for chunk in chat(req.session_id, req.pid, req.question):
            yield chunk.encode()

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",  # Disable Nginx buffering
        },
    )


@app.post("/clear")
def clear_endpoint(
    req: ClearRequest,
    x_copilot_secret: str | None = Header(default=None),
):
    _require_auth(x_copilot_secret)
    clear_conversation(req.session_id)
    return {"cleared": True, "session_id": req.session_id}


@app.post("/v2/query")
def v2_query_endpoint(
    req: V2QueryRequest,
    x_copilot_secret: str | None = Header(default=None),
):
    """LangGraph supervisor graph: document ingestion + guideline retrieval."""
    _require_auth(x_copilot_secret)

    if not req.query.strip():
        raise HTTPException(status_code=400, detail="Query cannot be empty")
    if req.pid <= 0:
        raise HTTPException(status_code=400, detail="Invalid patient ID")
    if req.file_path and req.doc_type not in ("lab_pdf", "intake_form"):
        raise HTTPException(
            status_code=400,
            detail="doc_type must be 'lab_pdf' or 'intake_form' when file_path is provided",
        )

    try:
        result = run_graph(
            patient_id=req.pid,
            query=req.query,
            file_path=req.file_path,
            doc_type=req.doc_type,
        )
    except (ValueError, FileNotFoundError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail="Graph execution failed") from exc

    return result


@app.post("/v2/ingest")
async def ingest_endpoint(
    file: UploadFile = File(...),
    doc_type: str = Form(...),
    pid: int = Form(...),
    x_copilot_secret: str | None = Header(default=None),
):
    """Upload a PDF/image, extract structured data, and import to patient chart."""
    _require_auth(x_copilot_secret)

    if doc_type not in ("lab_pdf", "intake_form"):
        raise HTTPException(status_code=400, detail="doc_type must be 'lab_pdf' or 'intake_form'")
    if pid <= 0:
        raise HTTPException(status_code=400, detail="Invalid patient ID")

    suffix = Path(file.filename).suffix if file.filename else ".pdf"
    tmp_path = None
    try:
        content = await file.read()
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            tmp.write(content)
            tmp_path = tmp.name
        result = attach_and_extract(pid, tmp_path, doc_type)
        return {"status": "ok", "pid": pid, "doc_type": doc_type, "extracted": result}
    except (ValueError, FileNotFoundError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail="Extraction failed") from exc
    finally:
        if tmp_path and os.path.exists(tmp_path):
            os.unlink(tmp_path)


@app.get("/logs")
def get_logs(
    n: int = 50,
    x_copilot_secret: str | None = Header(default=None),
):
    """Return the last N log entries from the observability log."""
    _require_auth(x_copilot_secret)

    if not os.path.exists(LOG_FILE):
        return {"entries": [], "message": "No log file yet"}

    try:
        with open(LOG_FILE, "r") as f:
            lines = f.readlines()
        recent = lines[-n:] if len(lines) > n else lines
        entries = []
        for line in recent:
            try:
                entries.append(json.loads(line.strip()))
            except Exception:
                pass
        return {"entries": entries, "total_lines": len(lines)}
    except Exception as e:
        return {"error": str(e)}
