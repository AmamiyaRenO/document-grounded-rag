"""Pydantic request/response models for the ``POST /ask`` endpoint."""

from __future__ import annotations

from pydantic import BaseModel, Field


class AskRequest(BaseModel):
    question: str = Field(..., min_length=1, description="The user's natural-language question.")


class EvidenceItem(BaseModel):
    document_id: str
    chunk_id: str
    similarity_score: float


class AskResponse(BaseModel):
    answer: str
    evidence_used: list[EvidenceItem]
    evidence_sufficient: bool
    guardrail_triggered: bool
