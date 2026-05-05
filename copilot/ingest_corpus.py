"""One-time script: fetch → section-chunk → embed → index guideline corpus.

Run after initial deployment or when corpus docs are updated:
    python ingest_corpus.py

Sources:
  ada-standards-2024   — requires manual download (journal blocks scrapers)
                         See ADA entry below for instructions.
  jnc8-2014            — fetched from PubMed Central (public, static HTML)
  uspstf-hypertension  — fetched from USPSTF (Next.js SSR, extracted from __NEXT_DATA__)

Patient data never enters this index — guideline corpus only.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path

import httpx
from bs4 import BeautifulSoup

from retriever import chunk_and_index, get_retriever

_MIN_CHUNK_CHARS = 80

_HEADERS = {
    "User-Agent": "ClinicalCopilot-Ingest/1.0 (+https://clinicalcopilot.org)",
    "Accept": "text/html,application/xhtml+xml",
}

# ---------------------------------------------------------------------------
# Corpus definition
#
# Each entry must have ONE of:
#   url       — fetched with httpx (set next_data=True for Next.js pages)
#   text_path — path to a plain-text file with the content pre-saved manually
#
# css_selector restricts parsing to a specific DOM subtree (saves noise).
# ---------------------------------------------------------------------------

CORPUS: list[dict] = [
    {
        "source_id": "ada-standards-2024",
        "title": "ADA Standards of Care 2024 — Glycemic Goals & Key Recommendations",
        # diabetesjournals.org and professional.diabetes.org block automated fetches.
        # Manual steps to populate corpus/ada-standards-2024.txt:
        #   1. Open https://professional.diabetes.org/standards (free ADA account required)
        #      OR https://diabetesjournals.org/care/issue/47/Supplement_1
        #   2. Copy the text of sections: Glycemic Goals, Classification & Diagnosis,
        #      Pharmacologic Approaches, and Comorbidities.
        #   3. Save as plain text to copilot/corpus/ada-standards-2024.txt
        # Relevant demo patient: Ted Shaw (T2DM, HbA1c target)
        "text_path": os.environ.get("ADA_TEXT_PATH", "corpus/ada-standards-2024.txt"),
        "section_tags": ["h2", "h3"],
    },
    {
        "source_id": "jnc8-2014",
        "title": "JNC 8 Hypertension Guidelines (JAMA 2014)",
        # Full text freely available on PubMed Central.
        # Relevant demo patients: Ted Shaw (HTN), Jim Moses (post-MI/HTN)
        "url": "https://pmc.ncbi.nlm.nih.gov/articles/PMC4132556/",
        "css_selector": "#mc",  # PMC article body container
        "section_tags": ["h2", "h3", "h4"],
    },
    {
        "source_id": "uspstf-hypertension",
        "title": "USPSTF Hypertension in Adults: Screening Recommendation",
        # Next.js SSR page — content extracted from __NEXT_DATA__ JSON blob.
        # Relevant demo patients: Ted Shaw, Jim Moses
        "url": "https://www.uspreventiveservicestaskforce.org/uspstf/recommendation/hypertension-in-adults-screening",
        "next_data": True,
    },
]


# ---------------------------------------------------------------------------
# Fetching
# ---------------------------------------------------------------------------

def _fetch_html(url: str) -> str:
    resp = httpx.get(url, headers=_HEADERS, follow_redirects=True, timeout=30)
    resp.raise_for_status()
    return resp.text


def _extract_next_data_text(html: str) -> str:
    """Pull readable text out of a Next.js __NEXT_DATA__ JSON blob."""
    m = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', html, re.DOTALL)
    if not m:
        # Fall back to plain HTML parse
        return BeautifulSoup(html, "html.parser").get_text(separator="\n", strip=True)
    try:
        data = json.loads(m.group(1))
    except json.JSONDecodeError:
        return ""
    # Walk the JSON tree collecting all string values longer than 60 chars
    parts: list[str] = []

    def _walk(node: object) -> None:
        if isinstance(node, str) and len(node) > 60:
            parts.append(node.strip())
        elif isinstance(node, list):
            for item in node:
                _walk(item)
        elif isinstance(node, dict):
            for v in node.values():
                _walk(v)

    _walk(data)
    return "\n\n".join(parts)


# ---------------------------------------------------------------------------
# Chunking
# ---------------------------------------------------------------------------

@dataclass
class RawChunk:
    source_id: str
    section: str
    text: str


def _chunk_html(html: str, source_id: str, section_tags: list[str],
                css_selector: str | None) -> list[RawChunk]:
    soup = BeautifulSoup(html, "html.parser")
    root = soup.select_one(css_selector) if css_selector else soup
    if root is None:
        root = soup

    headers = root.find_all(section_tags)
    if not headers:
        text = root.get_text(separator="\n", strip=True)
        if len(text) >= _MIN_CHUNK_CHARS:
            return [RawChunk(source_id=source_id, section="full", text=text)]
        return []

    chunks: list[RawChunk] = []
    for header in headers:
        title = header.get_text(strip=True)
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
        if body and len(body) >= _MIN_CHUNK_CHARS:
            chunks.append(RawChunk(
                source_id=source_id,
                section=title,
                text=f"{title}\n\n{body}",
            ))
    return chunks


def _chunk_plain_text(text: str, source_id: str) -> list[RawChunk]:
    """Split plain text on blank lines or markdown-style headers."""
    sections = re.split(r'\n{2,}|(?=\n#{1,3} )', text)
    chunks: list[RawChunk] = []
    for section in sections:
        section = section.strip()
        if len(section) < _MIN_CHUNK_CHARS:
            continue
        first_line = section.splitlines()[0].lstrip("#").strip()
        chunks.append(RawChunk(source_id=source_id, section=first_line, text=section))
    return chunks


# ---------------------------------------------------------------------------
# Main ingest
# ---------------------------------------------------------------------------

def ingest() -> None:
    os.makedirs("corpus", exist_ok=True)
    retriever = get_retriever()
    total_new = 0

    for doc in CORPUS:
        sid = doc["source_id"]
        print(f"\n── {doc['title']}")

        # --- Acquire content ---
        if "text_path" in doc:
            path = Path(doc["text_path"])
            if not path.exists():
                print(f"  SKIP: {path} not found — see inline instructions to create it.",
                      file=sys.stderr)
                continue
            raw_text = path.read_text(encoding="utf-8")
            chunks = _chunk_plain_text(raw_text, sid)

        elif doc.get("next_data"):
            print(f"  Fetching (Next.js) {doc['url']} …")
            try:
                html = _fetch_html(doc["url"])
            except Exception as exc:
                print(f"  WARN: fetch failed: {exc}", file=sys.stderr)
                continue
            raw_text = _extract_next_data_text(html)
            chunks = _chunk_plain_text(raw_text, sid)

        else:
            print(f"  Fetching {doc['url']} …")
            try:
                html = _fetch_html(doc["url"])
            except Exception as exc:
                print(f"  WARN: fetch failed: {exc}", file=sys.stderr)
                continue
            chunks = _chunk_html(
                html, sid,
                doc.get("section_tags", ["h2", "h3"]),
                doc.get("css_selector"),
            )

        if not chunks:
            print(f"  WARN: no chunks extracted from {sid}", file=sys.stderr)
            continue

        # --- Index via retriever ---
        indexed = retriever.index_documents([
            {
                "id": hashlib.sha256(f"{c.source_id}:{c.section}:{c.text[:80]}".encode()).hexdigest()[:16],
                "text": c.text,
                "metadata": {"source_id": c.source_id, "section": c.section, "title": doc["title"]},
            }
            for c in chunks
        ])
        total_new += indexed
        print(f"  {sid}: {len(chunks)} chunks extracted, {indexed} new added to index")

    print(f"\nDone. New chunks indexed this run: {total_new}")
    print(f"Total chunks in index: {retriever.count()}")


if __name__ == "__main__":
    ingest()
