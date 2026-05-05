#!/bin/sh
set -e
echo "[copilot] Indexing guideline corpus..."
python index_corpus.py
echo "[copilot] Starting service..."
exec uvicorn main:app --host 0.0.0.0 --port 8400 --log-level warning
