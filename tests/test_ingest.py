"""Ingestion/chunking unit tests: stable, well-formed document and chunk IDs."""

import re

from hfpef_rag.ingest import load_chunks


def test_chunks_have_well_formed_ids():
    chunks = load_chunks()
    assert chunks, "expected at least one chunk from the sample documents"

    doc_ids = {c.document_id for c in chunks}
    # The five bundled documents map to doc_1..doc_5.
    assert {"doc_1", "doc_2", "doc_3", "doc_4", "doc_5"} <= doc_ids

    for c in chunks:
        assert re.fullmatch(r"doc_\d+", c.document_id)
        assert re.fullmatch(r"chunk_\d+", c.chunk_id)
        assert c.title
        assert c.source_file.endswith((".md", ".txt"))
        assert c.text.strip()


def test_chunk_ids_restart_per_document():
    chunks = load_chunks()
    first_per_doc = {}
    for c in chunks:
        first_per_doc.setdefault(c.document_id, c.chunk_id)
    # Every document's first chunk is chunk_0.
    assert set(first_per_doc.values()) == {"chunk_0"}
