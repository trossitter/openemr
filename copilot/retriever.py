"""
Hybrid RAG retriever for clinical guidelines.

Pipeline:
  1. BM25 sparse retrieval  (rank-bm25, in-memory)
  2. Dense vector retrieval (ChromaDB, persistent)
  3. Cohere Rerank on merged candidates
  4. Return top-N RetrievedChunk objects with Citation metadata

Entry points:
  search_guidelines(query)   — used by the evidence-retriever worker
  chunk_and_index(...)       — used by index_corpus.py at build time
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass
from typing import Optional

import chromadb
import cohere
from rank_bm25 import BM25Okapi

from schemas import Citation

COHERE_API_KEY = os.environ.get("COHERE_API_KEY", "")
CHROMA_PERSIST_DIR = os.environ.get("CHROMA_PERSIST_DIR", "/data/chroma")
COLLECTION_NAME = "clinical_guidelines"

CHUNK_SIZE = 400      # approximate words per chunk
CHUNK_OVERLAP = 80
CANDIDATE_K = 20      # candidates fetched from each retriever before rerank
RERANK_TOP_N = 3      # chunks fed to the answer model


@dataclass
class RetrievedChunk:
    chunk_id: str
    text: str
    source_id: str    # e.g. "ada-2024", "jnc8", "uspstf"
    section: str
    score: float
    citation: Citation


def _tokenize(text: str) -> list[str]:
    return re.sub(r"[^a-zA-Z0-9]", " ", text.lower()).split()


def _chunk_text(
    text: str,
    source_id: str,
    section: str,
    size: int = CHUNK_SIZE,
    overlap: int = CHUNK_OVERLAP,
) -> list[dict]:
    words = text.split()
    chunks: list[dict] = []
    i = 0
    while i < len(words):
        window = words[i : i + size]
        chunks.append({
            "id": f"{source_id}_{len(chunks):04d}",
            "text": " ".join(window),
            "metadata": {
                "source_id": source_id,
                "section": section,
                "chunk_index": len(chunks),
            },
        })
        i += size - overlap
    return chunks


class HybridRetriever:
    def __init__(self, persist_dir: str = CHROMA_PERSIST_DIR) -> None:
        self._chroma = chromadb.PersistentClient(path=persist_dir)
        self._collection = self._chroma.get_or_create_collection(
            COLLECTION_NAME,
            metadata={"hnsw:space": "cosine"},
        )
        self._bm25: Optional[BM25Okapi] = None
        self._bm25_chunks: list[dict] = []
        self._cohere: Optional[cohere.Client] = (
            cohere.Client(api_key=COHERE_API_KEY) if COHERE_API_KEY else None
        )
        self._rebuild_bm25()

    # ------------------------------------------------------------------
    # Index management
    # ------------------------------------------------------------------

    def _rebuild_bm25(self) -> None:
        result = self._collection.get(include=["documents", "metadatas"])
        docs = result.get("documents") or []
        if not docs:
            return
        self._bm25_chunks = [
            {"id": cid, "text": doc, "metadata": meta}
            for cid, doc, meta in zip(result["ids"], docs, result["metadatas"])
        ]
        self._bm25 = BM25Okapi([_tokenize(c["text"]) for c in self._bm25_chunks])

    def index_documents(self, chunks: list[dict]) -> int:
        """Upsert chunks into ChromaDB + rebuild BM25. Returns count of new chunks added."""
        if not chunks:
            return 0
        existing = set(self._collection.get(ids=[c["id"] for c in chunks])["ids"])
        new = [c for c in chunks if c["id"] not in existing]
        if not new:
            return 0
        self._collection.add(
            ids=[c["id"] for c in new],
            documents=[c["text"] for c in new],
            metadatas=[c["metadata"] for c in new],
        )
        self._rebuild_bm25()
        return len(new)

    # ------------------------------------------------------------------
    # Retrieval
    # ------------------------------------------------------------------

    def _dense(self, query: str, k: int) -> list[dict]:
        count = self._collection.count()
        if count == 0:
            return []
        results = self._collection.query(query_texts=[query], n_results=min(k, count))
        return [
            {"id": cid, "text": doc, "metadata": meta, "score": 1.0 - dist}
            for cid, doc, meta, dist in zip(
                results["ids"][0],
                results["documents"][0],
                results["metadatas"][0],
                results["distances"][0],
            )
        ]

    def _sparse(self, query: str, k: int) -> list[dict]:
        if self._bm25 is None:
            return []
        scores = self._bm25.get_scores(_tokenize(query))
        top = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)[:k]
        return [
            {**self._bm25_chunks[i], "score": float(scores[i])}
            for i in top
            if scores[i] > 0
        ]

    def _merge(self, dense: list[dict], sparse: list[dict]) -> list[dict]:
        seen: dict[str, dict] = {}
        for chunk in dense + sparse:
            cid = chunk["id"]
            if cid not in seen or chunk["score"] > seen[cid]["score"]:
                seen[cid] = chunk
        return list(seen.values())

    def _rerank(self, query: str, candidates: list[dict], top_n: int) -> list[dict]:
        if not candidates:
            return []
        if self._cohere is None:
            return sorted(candidates, key=lambda c: c["score"], reverse=True)[:top_n]
        response = self._cohere.rerank(
            model="rerank-english-v3.0",
            query=query,
            documents=[c["text"] for c in candidates],
            top_n=min(top_n, len(candidates)),
        )
        return [
            {**candidates[r.index], "score": float(r.relevance_score)}
            for r in response.results
        ]

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def search(self, query: str, top_n: int = RERANK_TOP_N) -> list[RetrievedChunk]:
        half = CANDIDATE_K // 2
        candidates = self._merge(self._dense(query, half), self._sparse(query, half))
        reranked = self._rerank(query, candidates, top_n)

        results: list[RetrievedChunk] = []
        for item in reranked:
            meta = item["metadata"]
            source_id = meta.get("source_id", "unknown")
            section = meta.get("section", "")
            results.append(RetrievedChunk(
                chunk_id=item["id"],
                text=item["text"],
                source_id=source_id,
                section=section,
                score=item["score"],
                citation=Citation(
                    source_type="guideline",
                    source_id=source_id,
                    page_or_section=section,
                    field_or_chunk_id=item["id"],
                    quote_or_value=item["text"][:200],
                ),
            ))
        return results

    def count(self) -> int:
        return self._collection.count()


# ------------------------------------------------------------------
# Module-level singleton
# ------------------------------------------------------------------

_retriever: Optional[HybridRetriever] = None


def get_retriever() -> HybridRetriever:
    global _retriever
    if _retriever is None:
        _retriever = HybridRetriever()
    return _retriever


def search_guidelines(query: str, top_n: int = RERANK_TOP_N) -> list[RetrievedChunk]:
    """Primary entry point for the evidence-retriever worker."""
    return get_retriever().search(query, top_n)


def chunk_and_index(source_id: str, section: str, text: str) -> int:
    """Chunk a document section and add it to the index. Used by index_corpus.py."""
    return get_retriever().index_documents(_chunk_text(text, source_id, section))
