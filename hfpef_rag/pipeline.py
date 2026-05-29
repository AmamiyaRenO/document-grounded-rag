"""Request orchestration: guardrail -> retrieve -> evidence gate -> generate -> log.

Safety-first ordering: the urgent-symptom guardrail runs on the raw question before
any retrieval or LLM call, and short-circuits with an escalation message.
"""

from __future__ import annotations

import time
import uuid

from .answerability import assess_answerability
from .config import settings
from .evidence import INSUFFICIENT_MESSAGE, assess_evidence
from .generator import generate_answer
from .guardrails import check_guardrails
from .logging_store import write_log
from .retriever import retrieve
from .schemas import AskResponse, EvidenceItem
from .vector_store import RetrievedChunk


def _evidence_items(results: list[RetrievedChunk]) -> list[EvidenceItem]:
    return [
        EvidenceItem(
            document_id=r.chunk.document_id,
            chunk_id=r.chunk.chunk_id,
            similarity_score=r.similarity_score,
        )
        for r in results
    ]


def _guardrail_log_fields(guardrail) -> dict[str, object]:
    fields: dict[str, object] = {
        "guardrail_source": guardrail.source,
    }
    if guardrail.matched_terms:
        fields["guardrail_matched_terms"] = guardrail.matched_terms
    if guardrail.semantic_risk is not None or guardrail.semantic_error:
        fields["semantic_guardrail_model"] = settings.ollama_risk_model
    if guardrail.semantic_risk is not None:
        fields["semantic_guardrail_risk"] = guardrail.semantic_risk
    if guardrail.semantic_confidence is not None:
        fields["semantic_guardrail_confidence"] = guardrail.semantic_confidence
    if guardrail.semantic_reason:
        fields["semantic_guardrail_reason"] = guardrail.semantic_reason
    if guardrail.semantic_error:
        fields["semantic_guardrail_error"] = guardrail.semantic_error
    return fields


def _answerability_log_fields(answerability) -> dict[str, object]:
    fields: dict[str, object] = {
        "answerability_checked": answerability.checked,
        "answerability_sufficient": answerability.sufficient,
        "answerability_reason": answerability.reason,
    }
    if answerability.model_name:
        fields["answerability_model"] = answerability.model_name
    if answerability.prompt_summary:
        fields["answerability_prompt_summary"] = answerability.prompt_summary
    return fields


def answer_question(question: str) -> AskResponse:
    started = time.perf_counter()
    request_id = str(uuid.uuid4())

    base_log = {
        "request_id": request_id,
        "question": question,
    }

    # 1. Guardrail check (before any retrieval / generation).
    guardrail = check_guardrails(question)
    if guardrail.triggered:
        response = AskResponse(
            answer=guardrail.message or "",
            evidence_used=[],
            evidence_sufficient=False,
            guardrail_triggered=True,
        )
        write_log(
            {
                **base_log,
                "retrieved": [],
                "evidence_sufficient": False,
                "evidence_reason": "guardrail_short_circuit",
                "answerability_checked": False,
                "answerability_sufficient": False,
                "answerability_reason": "guardrail_short_circuit",
                "guardrail_triggered": True,
                **_guardrail_log_fields(guardrail),
                "answer": response.answer,
                "model_name": None,
                "prompt_summary": None,
                "latency_ms": round((time.perf_counter() - started) * 1000, 1),
            }
        )
        return response

    # 2. Retrieve.
    results = retrieve(question)
    retrieved_log = [
        {
            "document_id": r.chunk.document_id,
            "chunk_id": r.chunk.chunk_id,
            "title": r.chunk.title,
            "similarity_score": r.similarity_score,
        }
        for r in results
    ]

    # 3. Evidence sufficiency gate.
    decision = assess_evidence(results)
    if not decision.sufficient:
        response = AskResponse(
            answer=INSUFFICIENT_MESSAGE,
            evidence_used=_evidence_items(results),
            evidence_sufficient=False,
            guardrail_triggered=False,
        )
        write_log(
            {
                **base_log,
                "retrieved": retrieved_log,
                "evidence_sufficient": False,
                "evidence_reason": decision.reason,
                "best_score": decision.best_score,
                "answerability_checked": False,
                "answerability_sufficient": False,
                "answerability_reason": "similarity_gate_failed",
                "guardrail_triggered": False,
                **_guardrail_log_fields(guardrail),
                "answer": response.answer,
                "model_name": None,
                "prompt_summary": None,
                "latency_ms": round((time.perf_counter() - started) * 1000, 1),
            }
        )
        return response

    # 4. Optional answerability check.
    answerability = assess_answerability(question, results)
    if not answerability.sufficient:
        response = AskResponse(
            answer=INSUFFICIENT_MESSAGE,
            evidence_used=_evidence_items(results),
            evidence_sufficient=False,
            guardrail_triggered=False,
        )
        write_log(
            {
                **base_log,
                "retrieved": retrieved_log,
                "evidence_sufficient": False,
                "evidence_reason": "answerability_gate_failed",
                "best_score": decision.best_score,
                **_answerability_log_fields(answerability),
                "guardrail_triggered": False,
                **_guardrail_log_fields(guardrail),
                "answer": response.answer,
                "model_name": None,
                "prompt_summary": None,
                "latency_ms": round((time.perf_counter() - started) * 1000, 1),
            }
        )
        return response

    # 5. Generate grounded answer.
    generation = generate_answer(question, results)
    response = AskResponse(
        answer=generation.answer,
        evidence_used=_evidence_items(results),
        evidence_sufficient=True,
        guardrail_triggered=False,
    )

    # 6. Log everything.
    write_log(
        {
            **base_log,
            "retrieved": retrieved_log,
            "evidence_sufficient": True,
            "evidence_reason": decision.reason,
            "best_score": decision.best_score,
            **_answerability_log_fields(answerability),
            "guardrail_triggered": False,
            **_guardrail_log_fields(guardrail),
            "answer": response.answer,
            "model_name": generation.model_name,
            "prompt_summary": generation.prompt_summary,
            "latency_ms": round((time.perf_counter() - started) * 1000, 1),
        }
    )
    return response
