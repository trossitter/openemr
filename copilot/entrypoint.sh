#!/bin/sh
set -e

# Warn early so `docker logs copilot-service` gives an actionable message
if [ -z "$ANTHROPIC_API_KEY" ]; then
    echo "[copilot] WARNING: ANTHROPIC_API_KEY is not set — chat will fail at runtime"
fi
if [ -z "$COHERE_API_KEY" ]; then
    echo "[copilot] WARNING: COHERE_API_KEY is not set — RAG reranking will be disabled"
fi

echo "[copilot] Indexing guideline corpus..."
python index_corpus.py
echo "[copilot] Warming up embedding model (downloads ONNX on first run)..."
python -c "from retriever import search_guidelines; search_guidelines('warmup', top_n=1)" 2>&1 | grep -v "^/" || true
echo "[copilot] Warmup complete."
echo "[copilot] Starting service..."
exec uvicorn main:app --host 0.0.0.0 --port 8400 --log-level warning
