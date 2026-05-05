"""Hybrid retriever for the clinical guideline corpus.

Dense (ChromaDB cosine) + Sparse (BM25) → combined score → Cohere Rerank → top-3.
Patient data never enters this index — guideline corpus only.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Optional

import cohere
import chromadb
import numpy as np
from chromadb.utils.embedding_functions import DefaultEmbeddingFunction
from rank_bm25 import BM25Okapi

from schemas import Citation

CHROMA_PERSIST_DIR = os.environ.get("CHROMA_PERSIST_DIR", "/data/chroma")
COHERE_API_KEY = os.environ.get("COHERE_API_KEY", "")
COLLECTION_NAME = "guideline_corpus"

_TOP_K_CANDIDATES = 10
_TOP_K_FINAL = 3
_DENSE_WEIGHT = 0.5  # linear blend: α·dense + (1-α)·bm25


@dataclass
class RetrievedChunk:
    text: str
    citation: Citation
    relevance_score: float


class GuidelineRetriever:
    """Hybrid dense+sparse retriever with Cohere reranking.

    Call retrieve(query) to get up to 3 reranked guideline chunks.
    BM25 index is built in-memory from ChromaDB on first use and rebuilt
    via rebuild_index() after corpus updates.
    """

    def __init__(self) -> None:
        self._ef = DefaultEmbeddingFunction()
        self._chroma = chromadb.PersistentClient(path=CHROMA_PERSIST_DIR)
        self._collection = self._chroma.get_or_create_collection(
            name=COLLECTION_NAME,
            embedding_function=self._ef,
            metadata={"hnsw:space": "cosine"},
        )
        self._cohere: Optional[cohere.ClientV2] = (
            cohere.ClientV2(api_key=COHERE_API_KEY) if COHERE_API_KEY else None
        )
        self._bm25: Optional[BM25Okapi] = None
        self._bm25_docs: list[dict] = []
        self._rebuild_bm25()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def retrieve(self, query: str) -> list[RetrievedChunk]:
        """Return up to _TOP_K_FINAL reranked chunks for *query*."""
        if not self._bm25_docs:
            return []

        n = min(_TOP_K_CANDIDATES, len(self._bm25_docs))
        candidates = self._hybrid_candidates(query, n)

        if self._cohere and candidates:
            return self._cohere_rerank(query, candidates)

        return [self._to_chunk(doc, score) for doc, score in candidates[:_TOP_K_FINAL]]

    def rebuild_index(self) -> None:
        """Reload BM25 index from ChromaDB (call after re-ingestion)."""
        self._rebuild_bm25()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _rebuild_bm25(self) -> None:
        result = self._collection.get(include=["documents", "metadatas"])
        docs: list[str] = result.get("documents") or []
        metas: list[dict] = result.get("metadatas") or []
        ids: list[str] = result.get("ids") or []
        if not docs:
            self._bm25 = None
            self._bm25_docs = []
            return
        self._bm25 = BM25Okapi([d.lower().split() for d in docs])
        self._bm25_docs = [
            {"id": id_, "text": text, "metadata": meta}
            for id_, text, meta in zip(ids, docs, metas)
        ]

    def _hybrid_candidates(
        self, query: str, n: int
    ) -> list[tuple[dict, float]]:
        # Dense
        dense_result = self._collection.query(
            query_texts=[query],
            n_results=n,
            include=["documents", "metadatas", "distances"],
        )
        dense_ids: list[str] = dense_result["ids"][0]
        # cosine distance ∈ [0,2]; convert to similarity ∈ [0,1]
        dense_scores: dict[str, float] = {
            id_: max(0.0, 1.0 - float(dist))
            for id_, dist in zip(dense_ids, dense_result["distances"][0])
        }

        # Sparse (BM25)
        assert self._bm25 is not None
        raw: np.ndarray = self._bm25.get_scores(query.lower().split())
        max_bm25 = float(raw.max()) if raw.size else 1.0
        bm25_scores: dict[str, float] = {
            doc["id"]: float(score / max_bm25) if max_bm25 > 0 else 0.0
            for doc, score in zip(self._bm25_docs, raw)
        }

        # Linear combination
        all_ids = set(dense_scores) | set(bm25_scores)
        ranked: list[tuple[str, float]] = sorted(
            (
                (id_, _DENSE_WEIGHT * dense_scores.get(id_, 0.0)
                 + (1 - _DENSE_WEIGHT) * bm25_scores.get(id_, 0.0))
                for id_ in all_ids
            ),
            key=lambda x: x[1],
            reverse=True,
        )

        id_to_doc = {d["id"]: d for d in self._bm25_docs}
        return [
            (id_to_doc[id_], score)
            for id_, score in ranked[:n]
            if id_ in id_to_doc
        ]

    def _cohere_rerank(
        self, query: str, candidates: list[tuple[dict, float]]
    ) -> list[RetrievedChunk]:
        assert self._cohere is not None
        texts = [doc["text"] for doc, _ in candidates]
        resp = self._cohere.rerank(
            model="rerank-english-v3.0",
            query=query,
            documents=texts,
            top_n=_TOP_K_FINAL,
        )
        return [
            self._to_chunk(candidates[r.index][0], r.relevance_score)
            for r in resp.results
        ]

    @staticmethod
    def _to_chunk(doc: dict, score: float) -> RetrievedChunk:
        meta = doc["metadata"]
        citation = Citation(
            source_type="guideline",
            source_id=meta.get("source_id", ""),
            page_or_section=meta.get("section", ""),
            field_or_chunk_id=doc["id"],
            quote_or_value=doc["text"][:300],
            bbox=None,
        )
        return RetrievedChunk(text=doc["text"], citation=citation, relevance_score=score)
