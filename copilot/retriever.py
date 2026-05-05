"""Hybrid RAG retriever: BM25 (sparse) + ChromaDB (dense) → Cohere rerank.

Usage:
    from retriever import get_retriever
    chunks = get_retriever().retrieve("HbA1c target for T2DM patient", final_k=3)
"""
from __future__ import annotations

import os
from typing import TypedDict

import chromadb
import cohere
from rank_bm25 import BM25Okapi

from config import ANTHROPIC_API_KEY  # noqa: F401 — ensure config is loaded first

COHERE_API_KEY: str = os.environ.get("COHERE_API_KEY", "")
CHROMA_PERSIST_DIR: str = os.environ.get("CHROMA_PERSIST_DIR", "/tmp/copilot-chroma")

_EMBED_MODEL = "embed-english-v3.0"
_RERANK_MODEL = "rerank-english-v3.0"
_COLLECTION_NAME = "guidelines"


class GuidelineChunk(TypedDict):
    text: str
    source_type: str
    source_id: str
    page_or_section: str
    field_or_chunk_id: str


class HybridRetriever:
    """
    Retrieves guideline evidence with BM25 + dense vector search merged by union,
    then reranked by Cohere. Patient data is never indexed here.
    """

    def __init__(self) -> None:
        if not COHERE_API_KEY:
            raise RuntimeError(
                "COHERE_API_KEY is not set. Get a free key at cohere.com."
            )
        self._co = cohere.Client(api_key=COHERE_API_KEY)
        chroma = chromadb.PersistentClient(path=CHROMA_PERSIST_DIR)
        # No EmbeddingFunction passed — we embed manually so we can use
        # different Cohere input_type for documents vs queries.
        self._col = chroma.get_or_create_collection(
            name=_COLLECTION_NAME,
            metadata={"hnsw:space": "cosine"},
        )
        self._chunks: list[GuidelineChunk] = []
        self._bm25: BM25Okapi | None = None

    # ── Embedding helpers ──────────────────────────────────────────────────

    def _embed_docs(self, texts: list[str]) -> list[list[float]]:
        resp = self._co.embed(
            texts=texts,
            model=_EMBED_MODEL,
            input_type="search_document",
        )
        return resp.embeddings

    def _embed_query(self, text: str) -> list[float]:
        resp = self._co.embed(
            texts=[text],
            model=_EMBED_MODEL,
            input_type="search_query",
        )
        return resp.embeddings[0]

    # ── Index management ───────────────────────────────────────────────────

    def build(self, chunks: list[GuidelineChunk], force: bool = False) -> None:
        """Index chunks. If the collection already has data and force=False, reload from it."""
        if self._col.count() > 0 and not force:
            self._reload_from_chroma()
            return

        if force and self._col.count() > 0:
            self._col.delete(ids=self._col.get()["ids"])

        texts = [c["text"] for c in chunks]
        embeddings = self._embed_docs(texts)
        metadatas = [{k: v for k, v in c.items() if k != "text"} for c in chunks]

        self._col.add(
            ids=[c["field_or_chunk_id"] for c in chunks],
            documents=texts,
            embeddings=embeddings,
            metadatas=metadatas,
        )
        self._chunks = list(chunks)
        self._bm25 = BM25Okapi([t.split() for t in texts])

    def _reload_from_chroma(self) -> None:
        """Reconstruct in-memory state from a previously persisted collection."""
        existing = self._col.get(include=["documents", "metadatas"])
        self._chunks = [
            {**meta, "text": doc}  # type: ignore[misc]
            for meta, doc in zip(existing["metadatas"], existing["documents"])
        ]
        self._bm25 = BM25Okapi([c["text"].split() for c in self._chunks])

    # ── Retrieval ──────────────────────────────────────────────────────────

    def retrieve(
        self,
        query: str,
        candidate_k: int = 10,
        final_k: int = 3,
    ) -> list[dict]:
        """
        Returns up to final_k reranked guideline chunks with citation metadata.

        Each result dict has: text, source_type, source_id, page_or_section,
        field_or_chunk_id, quote_or_value, bbox (None), rerank_score.
        """
        if not self._chunks or self._bm25 is None:
            raise RuntimeError("Index is empty. Call build() before retrieve().")

        n = len(self._chunks)
        k = min(candidate_k, n)

        # Dense: query ChromaDB with the pre-embedded query vector
        q_embed = self._embed_query(query)
        dense_result = self._col.query(
            query_embeddings=[q_embed],
            n_results=k,
            include=["metadatas"],
        )
        dense_ids: set[str] = set(dense_result["ids"][0])

        # Sparse: BM25 top-k by score
        bm25_scores = self._bm25.get_scores(query.split())
        sparse_ids: set[str] = {
            self._chunks[i]["field_or_chunk_id"]
            for i, _ in sorted(enumerate(bm25_scores), key=lambda x: x[1], reverse=True)[:k]
        }

        # Union of dense + sparse candidates
        candidate_ids = dense_ids | sparse_ids
        candidates = [c for c in self._chunks if c["field_or_chunk_id"] in candidate_ids]

        if not candidates:
            return []

        # Rerank with Cohere
        top_n = min(final_k, len(candidates))
        reranked = self._co.rerank(
            query=query,
            documents=[c["text"] for c in candidates],
            model=_RERANK_MODEL,
            top_n=top_n,
        )

        return [
            {
                "text": candidates[r.index]["text"],
                "source_type": candidates[r.index]["source_type"],
                "source_id": candidates[r.index]["source_id"],
                "page_or_section": candidates[r.index]["page_or_section"],
                "field_or_chunk_id": candidates[r.index]["field_or_chunk_id"],
                "quote_or_value": candidates[r.index]["text"][:200],
                "bbox": None,
                "rerank_score": r.relevance_score,
            }
            for r in reranked.results
        ]


# ── Module-level singleton ─────────────────────────────────────────────────

_retriever: HybridRetriever | None = None


def get_retriever() -> HybridRetriever:
    """Return the shared HybridRetriever, building the index on first call."""
    global _retriever
    if _retriever is None:
        from corpus import CORPUS_CHUNKS  # lazy import to avoid circular
        _retriever = HybridRetriever()
        _retriever.build(CORPUS_CHUNKS)
    return _retriever
