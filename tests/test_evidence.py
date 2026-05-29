"""Evidence-gate unit tests (no embeddings needed — uses synthetic scores)."""

from hfpef_rag.config import settings
from hfpef_rag.evidence import assess_evidence
from hfpef_rag.ingest import Chunk
from hfpef_rag.vector_store import RetrievedChunk


def _result(score: float) -> RetrievedChunk:
    chunk = Chunk(
        document_id="doc_1",
        chunk_id="chunk_0",
        title="t",
        source_file="doc_1.md",
        text="x",
    )
    return RetrievedChunk(chunk=chunk, similarity_score=score)


def test_empty_results_are_insufficient():
    decision = assess_evidence([])
    assert decision.sufficient is False
    assert decision.reason == "no_chunks_retrieved"


def test_strong_evidence_is_sufficient():
    results = [_result(0.72), _result(0.55), _result(0.40)]
    decision = assess_evidence(results)
    assert decision.sufficient is True
    assert decision.best_score == 0.72


def test_low_best_score_is_insufficient():
    below = settings.primary_threshold - 0.05
    decision = assess_evidence([_result(below), _result(below - 0.1)])
    assert decision.sufficient is False
    assert "primary_threshold" in decision.reason
