#!/usr/bin/env python3
"""
Index the clinical guideline corpus into ChromaDB.

Usage:
    python index_corpus.py [--corpus-dir PATH]

Reads .txt files from copilot/corpus/ by default.
Expected filenames: ada_2024.txt, jnc8.txt, uspstf.txt

Run once before starting the service, or re-run to pick up updated files
(existing chunks with matching IDs are skipped — safe to re-run).
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from retriever import chunk_and_index  # noqa: E402 (path insert above)

SOURCE_ID_MAP: dict[str, str] = {
    "ada_2024": "ada-2024",
    "jnc8": "jnc8",
    "uspstf": "uspstf",
}

_HEADING = re.compile(r"^(#{1,3}\s+.+|[A-Z][A-Z\s]{4,}:?)\s*$", re.MULTILINE)


def _split_sections(text: str) -> list[tuple[str, str]]:
    """Split on markdown headings or ALL-CAPS section titles."""
    parts = _HEADING.split(text)
    if len(parts) < 3:
        return [("full-document", text.strip())]
    sections: list[tuple[str, str]] = []
    for i in range(1, len(parts) - 1, 2):
        heading = parts[i].strip()
        body = parts[i + 1].strip() if i + 1 < len(parts) else ""
        if body:
            sections.append((heading, body))
    return sections or [("full-document", text.strip())]


def index_file(path: Path) -> int:
    source_id = SOURCE_ID_MAP.get(path.stem, path.stem.replace("_", "-"))
    text = path.read_text(encoding="utf-8")
    sections = _split_sections(text)
    total = 0
    for section, content in sections:
        added = chunk_and_index(source_id, section, content)
        total += added
        if added:
            print(f"  [{source_id}] {section[:60]!r}: +{added} chunks")
    return total


def main() -> None:
    parser = argparse.ArgumentParser(description="Index clinical guidelines into ChromaDB")
    parser.add_argument(
        "--corpus-dir",
        default=str(Path(__file__).parent / "corpus"),
        help="Directory containing .txt guideline files",
    )
    args = parser.parse_args()

    corpus_dir = Path(args.corpus_dir)
    if not corpus_dir.exists():
        print(f"ERROR: corpus directory not found: {corpus_dir}")
        print("Create copilot/corpus/ and populate ada_2024.txt, jnc8.txt, uspstf.txt")
        sys.exit(1)

    txt_files = sorted(corpus_dir.glob("*.txt"))
    if not txt_files:
        print(f"ERROR: no .txt files found in {corpus_dir}")
        sys.exit(1)

    print(f"Indexing {len(txt_files)} file(s) from {corpus_dir} ...\n")
    total = 0
    for path in txt_files:
        print(f"Processing: {path.name}")
        added = index_file(path)
        total += added
        print(f"  subtotal: {added} new chunks\n")

    print(f"Done. {total} chunks added to ChromaDB.")


if __name__ == "__main__":
    main()
