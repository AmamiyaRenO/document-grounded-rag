"""Optional LLM answerability check.

Similarity can show that retrieved chunks are topically related, but it cannot prove
that the chunks actually answer the user's question. This module adds a second,
optional gate after similarity passes and before answer generation.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from .config import settings
from .generator import _format_evidence
from .vector_store import RetrievedChunk

ANSWERABILITY_PROMPT_SUMMARY = (
    "Classify whether the retrieved evidence directly answers the user's question; "
    "return strict JSON with answerable, reason, and missing_information."
)

ANSWERABILITY_SYSTEM_PROMPT = (
    "You are an evidence answerability checker for a document-grounded health assistant.\n"
    "Your job is NOT to answer the user's question. Decide whether the supplied evidence "
    "directly contains enough information to answer the question safely.\n"
    "Return only strict JSON with this schema:\n"
    '{"answerable":true,"reason":"short explanation","missing_information":"short note"}\n'
    "Use answerable=false when the evidence is merely topically related but does not address "
    "the specific claim, treatment, cure, supplement, dose, comparison, or recommendation "
    "being asked about."
)


@dataclass
class AnswerabilityDecision:
    checked: bool
    sufficient: bool
    reason: str
    model_name: str | None = None
    prompt_summary: str | None = None


def _extract_json_object(text: str) -> dict[str, Any]:
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")
        if start == -1 or end == -1 or end <= start:
            raise
        parsed = json.loads(text[start : end + 1])
    if not isinstance(parsed, dict):
        raise ValueError("answerability response was not a JSON object")
    return parsed


def _check_with_openai(
    question: str, results: list[RetrievedChunk]
) -> AnswerabilityDecision:
    from openai import OpenAI

    model = settings.answerability_model or settings.llm_model
    client = OpenAI(api_key=settings.openai_api_key)
    user_content = (
        f"QUESTION:\n{question}\n\n"
        f"EVIDENCE:\n{_format_evidence(results)}"
    )
    completion = client.chat.completions.create(
        model=model,
        temperature=settings.answerability_temperature,
        max_tokens=settings.answerability_max_tokens,
        messages=[
            {"role": "system", "content": ANSWERABILITY_SYSTEM_PROMPT},
            {"role": "user", "content": user_content},
        ],
        response_format={"type": "json_object"},
    )
    raw = completion.choices[0].message.content or ""
    parsed = _extract_json_object(raw)
    answerable = bool(parsed.get("answerable", False))
    reason = str(parsed.get("reason") or parsed.get("missing_information") or "").strip()
    if not reason:
        reason = "LLM classified retrieved evidence as answerable." if answerable else (
            "LLM classified retrieved evidence as not answerable."
        )
    return AnswerabilityDecision(
        checked=True,
        sufficient=answerable,
        reason=reason,
        model_name=f"openai:{model}",
        prompt_summary=ANSWERABILITY_PROMPT_SUMMARY,
    )


def assess_answerability(
    question: str, results: list[RetrievedChunk]
) -> AnswerabilityDecision:
    """Return whether retrieved evidence actually answers the question.

    If the check is disabled or no OpenAI key is configured, treat the check as skipped
    and allow the pipeline to preserve the original offline behavior.
    """
    if not settings.answerability_check_enabled:
        return AnswerabilityDecision(
            checked=False,
            sufficient=True,
            reason="answerability_check_disabled",
        )
    if not settings.llm_enabled:
        return AnswerabilityDecision(
            checked=False,
            sufficient=True,
            reason="answerability_check_skipped_no_llm",
        )
    try:
        return _check_with_openai(question, results)
    except Exception as exc:  # noqa: BLE001 - fail open to preserve availability
        return AnswerabilityDecision(
            checked=True,
            sufficient=True,
            reason=f"answerability_check_error_fail_open: {type(exc).__name__}: {exc}",
            model_name=f"openai:{settings.answerability_model or settings.llm_model}",
            prompt_summary=ANSWERABILITY_PROMPT_SUMMARY,
        )
