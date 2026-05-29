"""Answer generation.

Two paths, selected automatically:

* **LLM path** (when ``OPENAI_API_KEY`` is set): a chat-completion call with a strict
  grounding prompt that forbids using anything beyond the supplied evidence.
* **Deterministic fallback** (no key, or the API call fails): an extractive answer
  assembled from the retrieved chunks. Fully offline and reproducible.

Either way the answer is grounded in the same retrieved chunks, and a standard
"general education / talk to your clinician" disclaimer is appended.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from .config import settings
from .vector_store import RetrievedChunk

DISCLAIMER = (
    "\n\n_This is general health education based on reference documents, not medical "
    "advice. Please talk with your own clinician about your situation._"
)

SYSTEM_PROMPT = (
    "You are a careful patient-education assistant for people learning about HFpEF "
    "(heart failure with preserved ejection fraction) and related cardiovascular-"
    "kidney-metabolic health.\n"
    "Rules:\n"
    "1. Answer ONLY using the EVIDENCE provided below. Do not add facts from outside "
    "the evidence.\n"
    "2. If the evidence does not contain the answer, say you don't have enough "
    "information rather than guessing.\n"
    "3. Do NOT give a personal diagnosis, specific drug doses, or individualized "
    "treatment instructions.\n"
    "4. Write in plain, warm, patient-friendly language at roughly an 8th-grade "
    "reading level. Keep it concise.\n"
    "5. Refer to the evidence by its [document_id/chunk_id] tags where helpful.\n"
    "6. End by encouraging the reader to talk with their own clinician."
)

# A short, human-readable summary of the prompt strategy, stored in the research log.
PROMPT_TEMPLATE_SUMMARY = (
    "system: patient-education assistant constrained to answer ONLY from supplied "
    "evidence chunks; no diagnosis/dosing; plain language; cite [doc/chunk]; defer to "
    "clinician. user: question + numbered evidence snippets with document_id/chunk_id."
)

DETERMINISTIC_MODEL_NAME = "deterministic-template-fallback"


@dataclass
class GenerationResult:
    answer: str
    model_name: str
    prompt_summary: str | None


def _format_evidence(results: list[RetrievedChunk]) -> str:
    blocks = []
    for r in results:
        tag = f"[{r.chunk.document_id}/{r.chunk.chunk_id}] (\"{r.chunk.title}\")"
        blocks.append(f"{tag}\n{r.chunk.text}")
    return "\n\n---\n\n".join(blocks)


def _generate_with_openai(question: str, results: list[RetrievedChunk]) -> str:
    from openai import OpenAI

    client = OpenAI(api_key=settings.openai_api_key)
    user_content = (
        f"QUESTION:\n{question}\n\n"
        f"EVIDENCE (use only this):\n{_format_evidence(results)}"
    )
    completion = client.chat.completions.create(
        model=settings.llm_model,
        temperature=settings.llm_temperature,
        max_tokens=settings.llm_max_tokens,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_content},
        ],
    )
    return completion.choices[0].message.content.strip()


_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+")

# Boilerplate (disclaimers, generic deferrals) we never want to surface as "the answer".
_BOILERPLATE = re.compile(
    r"(not medical advice|talk with your own clinician|general health education|"
    r"not specific to any individual|treatment decisions must be made|"
    r"use these questions as a starting point|paraphrased from public|disclaimer)",
    re.IGNORECASE,
)

_STOPWORDS = {
    "the", "a", "an", "and", "or", "of", "to", "in", "for", "on", "with", "about",
    "what", "which", "who", "is", "are", "do", "does", "should", "can", "could",
    "my", "me", "i", "you", "your", "it", "its", "be", "as", "at", "by", "that",
    "this", "these", "those", "from", "how", "when", "why", "will", "would",
}


def _clean_markdown(text: str) -> str:
    text = re.sub(r"^#+\s*", "", text, flags=re.MULTILINE)  # headings
    text = re.sub(r"^\s*[-*+]\s+", "", text, flags=re.MULTILINE)  # lists
    text = re.sub(r"[*_`>]", "", text)  # emphasis / quotes / code
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _tokens(text: str) -> set[str]:
    return {
        w
        for w in re.findall(r"[a-z0-9]+", text.lower())
        if len(w) > 2 and w not in _STOPWORDS
    }


def _definition_bonus(question: str, sentence: str) -> int:
    """Prefer definitional sentences for questions like "What is HFpEF?"."""
    lowered_question = question.lower()
    lowered_sentence = sentence.lower()
    asks_definition = re.search(r"\bwhat\s+(is|are)\b", lowered_question)
    looks_definitional = re.search(
        r"\b(is|are)\s+(a|an)\s+(type|condition|form|kind)\b|\bmeans\b|\brefers to\b",
        lowered_sentence,
    )
    return 1 if asks_definition and looks_definitional else 0


def _generate_deterministic(question: str, results: list[RetrievedChunk]) -> str:
    """Extractive fallback: pick the retrieved sentences most relevant to the question.

    Sentences are drawn from the top chunks, boilerplate/disclaimer lines are dropped,
    and the remainder are ranked by lexical overlap with the question (ties broken by
    original reading order). This keeps the answer responsive instead of echoing the
    documents' standing disclaimers.
    """
    query_terms = _tokens(question)
    candidates: list[tuple[int, int, float, int, str, str, str]] = []
    order = 0
    for r in results[: min(3, len(results))]:
        for sentence in _SENTENCE_SPLIT.split(_clean_markdown(r.chunk.text)):
            sentence = sentence.strip()
            order += 1
            if len(sentence) < 30 or _BOILERPLATE.search(sentence):
                continue
            overlap = len(query_terms & _tokens(sentence))
            candidates.append(
                (
                    overlap,
                    _definition_bonus(question, sentence),
                    r.similarity_score,
                    order,
                    sentence,
                    r.chunk.document_id,
                    r.chunk.chunk_id,
                )
            )

    if not candidates:
        return (
            "Here is what my reference documents say that relates to your question:\n\n"
            "- I could not extract a clear, relevant statement from the retrieved text."
        )

    # Rank by question overlap, definition fit, retrieval score, then reading order.
    ranked = sorted(candidates, key=lambda c: (-c[0], -c[1], -c[2], c[3]))[:5]

    bullets = [f"- {sent} [{doc}/{chunk}]" for _, _, _, _, sent, doc, chunk in ranked]
    intro = "Here is what my reference documents say that relates to your question:\n\n"
    return intro + "\n".join(bullets)


def generate_answer(
    question: str, results: list[RetrievedChunk]
) -> GenerationResult:
    """Generate a grounded answer, preferring the LLM and falling back gracefully."""
    if settings.llm_enabled:
        try:
            answer = _generate_with_openai(question, results)
            return GenerationResult(
                answer=answer + DISCLAIMER,
                model_name=f"openai:{settings.llm_model}",
                prompt_summary=PROMPT_TEMPLATE_SUMMARY,
            )
        except Exception as exc:  # noqa: BLE001 - fall back rather than 500 on API error
            answer = _generate_deterministic(question, results)
            return GenerationResult(
                answer=answer + DISCLAIMER,
                model_name=f"{DETERMINISTIC_MODEL_NAME} (openai_error: {type(exc).__name__})",
                prompt_summary=None,
            )

    answer = _generate_deterministic(question, results)
    return GenerationResult(
        answer=answer + DISCLAIMER,
        model_name=DETERMINISTIC_MODEL_NAME,
        prompt_summary=None,
    )
