"""One-time script: fetch → section-chunk → embed → index guideline corpus.

Run after initial deployment or when corpus docs are updated:
    python ingest_corpus.py

Chunks by HTML section headers (not sliding window).
Patient data never enters this index.
"""
from __future__ import annotations

import hashlib
import os
import sys
from dataclasses import dataclass

import chromadb
import httpx
from bs4 import BeautifulSoup
from chromadb.utils.embedding_functions import DefaultEmbeddingFunction

CHROMA_PERSIST_DIR = os.environ.get("CHROMA_PERSIST_DIR", "/data/chroma")
COLLECTION_NAME = "guideline_corpus"
_MIN_CHUNK_CHARS = 80

# Three curated guideline documents (per CONTEXT.md corpus spec)
CORPUS: list[dict] = [
    {
        "source_id": "ada-standards-2024",
        "title": "ADA Standards of Care 2024",
        "url": "https://diabetesjournals.org/care/issue/47/Supplement_1",
        "section_tags": ["h2", "h3"],
    },
    {
        "source_id": "jnc8-2014",
        "title": "JNC 8 Hypertension Guidelines (JAMA 2014, Tables 1-5)",
        "url": "https://jamanetwork.com/journals/jama/fullarticle/1791497",
        "section_tags": ["h2", "h3"],
    },
    {
        "source_id": "uspstf-recommendations",
        "title": "USPSTF Recommendations Summary Table",
        "url": "https://www.uspreventiveservicestaskforce.org/uspstf/recommendation-topics",
        "section_tags": ["h2", "h3"],
    },
]

_HEADERS = {
    "User-Agent": "ClinicalCopilot-Ingest/1.0 (+https://clinicalcopilot.org)",
    "Accept": "text/html,application/xhtml+xml",
}


@dataclass
class Chunk:
    source_id: str
    section: str
    text: str
    chunk_id: str


def _fetch_html(url: str) -> str:
    resp = httpx.get(url, headers=_HEADERS, follow_redirects=True, timeout=30)
    resp.raise_for_status()
    return resp.text


def _chunk_by_section(
    html: str, source_id: str, section_tags: list[str]
) -> list[Chunk]:
    """Split document into chunks at section headers, collecting trailing text."""
    soup = BeautifulSoup(html, "html.parser")
    chunks: list[Chunk] = []
    headers = soup.find_all(section_tags)

    if not headers:
        text = soup.get_text(separator="\n", strip=True)
        if len(text) >= _MIN_CHUNK_CHARS:
            cid = _chunk_id(source_id, "full")
            chunks.append(Chunk(source_id=source_id, section="full", text=text, chunk_id=cid))
        return chunks

    for header in headers:
        section_title = header.get_text(strip=True)
        parts: list[str] = []
        for sibling in header.next_siblings:
            if getattr(sibling, "name", None) in section_tags:
                break
            if hasattr(sibling, "get_text"):
                t = sibling.get_text(separator=" ", strip=True)
                if t:
                    parts.append(t)
            elif isinstance(sibling, str) and sibling.strip():
                parts.append(sibling.strip())

        body = " ".join(parts).strip()
        if not body or len(body) < _MIN_CHUNK_CHARS:
            continue

        text = f"{section_title}\n\n{body}"
        cid = _chunk_id(source_id, section_title)
        chunks.append(Chunk(source_id=source_id, section=section_title, text=text, chunk_id=cid))

    return chunks


def _chunk_id(source_id: str, section: str) -> str:
    return hashlib.sha256(f"{source_id}:{section}".encode()).hexdigest()[:16]


def ingest() -> None:
    client = chromadb.PersistentClient(path=CHROMA_PERSIST_DIR)
    ef = DefaultEmbeddingFunction()
    collection = client.get_or_create_collection(
        name=COLLECTION_NAME,
        embedding_function=ef,
        metadata={"hnsw:space": "cosine"},
    )

    total = 0
    for doc in CORPUS:
        print(f"Fetching: {doc['title']} …")
        try:
            html = _fetch_html(doc["url"])
        except Exception as exc:
            print(f"  WARN: fetch failed for {doc['source_id']}: {exc}", file=sys.stderr)
            continue

        chunks = _chunk_by_section(html, doc["source_id"], doc["section_tags"])
        if not chunks:
            print(f"  WARN: no chunks extracted from {doc['source_id']}", file=sys.stderr)
            continue

        print(f"  Upserting {len(chunks)} sections …")
        collection.upsert(
            ids=[c.chunk_id for c in chunks],
            documents=[c.text for c in chunks],
            metadatas=[
                {
                    "source_id": c.source_id,
                    "section": c.section,
                    "title": doc["title"],
                }
                for c in chunks
            ],
        )
        total += len(chunks)
        print(f"  OK — {doc['source_id']}: {len(chunks)} chunks")

    print(f"\nDone. Total chunks indexed: {total}")


if __name__ == "__main__":
    ingest()
