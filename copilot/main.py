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
from typing import AsyncGenerator

from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from agent import chat, clear_conversation, get_conversation_length
from config import COPILOT_SECRET, DEMO_MODE, LOG_FILE

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
