"""Load the sample documents and split them into citable chunks.

Each chunk carries a stable ``document_id`` (parsed from the ``doc_<n>_...`` filename),
a per-document ``chunk_id`` (``chunk_0``, ``chunk_1``, ...), the document title, the
source filename, and the chunk text.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from .config import DOCS_DIR, settings

_DOC_ID_RE = re.compile(r"^(doc_\d+)", re.IGNORECASE)


@dataclass(frozen=True)
class Chunk:
    document_id: str
    chunk_id: str
    title: str
    source_file: str
    text: str


def _document_id_for(path: Path) -> str:
    """Derive ``doc_<n>`` from the filename, falling back to the bare stem."""
    match = _DOC_ID_RE.match(path.stem)
    return match.group(1).lower() if match else path.stem


def _title_for(text: str, fallback: str) -> str:
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("#"):
            return line.lstrip("#").strip()
    return fallback


def _strip_boilerplate(text: str) -> str:
    """Remove blockquote disclaimer lines before chunking/embedding.

    The same legal disclaimer appears at the top of every document. Embedding it
    would (a) make every document's first chunk look alike and (b) let a meta-query
    match boilerplate instead of substance. The disclaimer is still preserved in the
    source files and is re-appended to every generated answer, so dropping it from the
    indexed text is safe and improves retrieval quality.
    """
    kept = [ln for ln in text.splitlines() if not ln.lstrip().startswith(">")]
    return "\n".join(kept)


def _split_into_chunks(text: str, size: int, overlap: int) -> list[str]:
    """Pack blank-line-separated paragraphs into ~``size``-char windows.

    Paragraphs are kept whole where possible; when adding the next paragraph would
    exceed ``size`` the current window is flushed and the new window starts with a
    short ``overlap`` tail from the previous window to preserve context across chunks.
    """
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    chunks: list[str] = []
    current = ""

    for para in paragraphs:
        if not current:
            current = para
        elif len(current) + len(para) + 2 <= size:
            current = f"{current}\n\n{para}"
        else:
            chunks.append(current)
            tail = current[-overlap:] if overlap > 0 else ""
            current = f"{tail}\n\n{para}".strip() if tail else para

    if current:
        chunks.append(current)
    return chunks


def load_chunks(docs_dir: Path | None = None) -> list[Chunk]:
    """Load every ``.md``/``.txt`` document under ``docs_dir`` and chunk it."""
    directory = docs_dir or DOCS_DIR
    paths = sorted(
        p for p in directory.iterdir() if p.suffix.lower() in {".md", ".txt"}
    )
    if not paths:
        raise FileNotFoundError(f"No .md or .txt documents found in {directory}")

    chunks: list[Chunk] = []
    for path in paths:
        text = path.read_text(encoding="utf-8")
        document_id = _document_id_for(path)
        title = _title_for(text, fallback=path.stem)
        pieces = _split_into_chunks(
            _strip_boilerplate(text),
            settings.chunk_size_chars,
            settings.chunk_overlap_chars,
        )
        for i, piece in enumerate(pieces):
            chunks.append(
                Chunk(
                    document_id=document_id,
                    chunk_id=f"chunk_{i}",
                    title=title,
                    source_file=path.name,
                    text=piece,
                )
            )
    return chunks
