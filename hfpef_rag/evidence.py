"""Evidence sufficiency gate.

Decides whether the retrieved chunks are strong enough to answer from. If not, the
pipeline refuses safely instead of generating a (possibly hallucinated) answer.

Rule:
    sufficient  <=>  best_score >= PRIMARY_THRESHOLD
                     AND count(score >= SUPPORT_THRESHOLD) >= MIN_SUPPORTING

Both thresholds and the minimum supporting count live in ``config.py`` and were
calibrated against the bundled sample documents.
"""

from __future__ import annotations

from dataclasses import dataclass

from .config import settings
from .vector_store import RetrievedChunk

INSUFFICIENT_MESSAGE = (
    "I don't have enough information in my reference documents to answer that reliably, "
    "so I'd rather not guess. The documents I can draw on cover HFpEF basics, treatment "
    "options, cardiovascular-kidney-metabolic health, warning signs, and questions to ask "
    "your doctor. You could try rephrasing your question around one of those topics, or "
    "ask your clinician or pharmacist, who can give advice specific to you."
)


@dataclass
class EvidenceDecision:
    sufficient: bool
    best_score: float
    supporting_count: int
    reason: str


def assess_evidence(results: list[RetrievedChunk]) -> EvidenceDecision:
    if not results:
        return EvidenceDecision(
            sufficient=False,
            best_score=0.0,
            supporting_count=0,
            reason="no_chunks_retrieved",
        )

    best_score = max(r.similarity_score for r in results)
    supporting = sum(
        1 for r in results if r.similarity_score >= settings.support_threshold
    )

    passes_primary = best_score >= settings.primary_threshold
    passes_support = supporting >= settings.min_supporting
    sufficient = passes_primary and passes_support

    if sufficient:
        reason = "sufficient"
    elif not passes_primary:
        reason = (
            f"best_score {best_score:.3f} < primary_threshold "
            f"{settings.primary_threshold}"
        )
    else:
        reason = (
            f"only {supporting} chunk(s) >= support_threshold "
            f"{settings.support_threshold}, need {settings.min_supporting}"
        )

    return EvidenceDecision(
        sufficient=sufficient,
        best_score=round(best_score, 4),
        supporting_count=supporting,
        reason=reason,
    )
