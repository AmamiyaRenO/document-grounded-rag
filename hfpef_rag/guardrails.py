"""Safety guardrail: detect urgent / high-risk queries.

This runs *before* retrieval and generation. The first layer is a deterministic
regex hard gate. If regex does not match, an optional offline semantic classifier
can ask a local Ollama model whether the question implies emergency risk.

Design note / limitation: both layers are safety aids, not medical triage. Regex
is auditable but shallow; the semantic layer can catch paraphrases, but it may
misclassify and therefore fails open on infrastructure or parsing errors.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any
from urllib import error, request

from .config import settings

# Each pattern is matched case-insensitively with word boundaries where appropriate.
# Patterns target the emergency symptoms named in the task plus common red flags.
_URGENT_PATTERNS: list[str] = [
    r"chest pain",
    r"chest pressure",
    r"chest tightness",
    r"chest discomfort",
    r"pressure in (my )?chest",
    r"crushing (weight|pressure|pain)",
    r"chest feels crushed",
    r"chest (feels )?(crushed|heavy)",
    r"severe shortness of breath",
    r"can('|no)?t breathe",
    r"cannot breathe",
    r"trouble breathing",
    r"struggling to breathe",
    r"gasping for air",
    r"faint(ing|ed)?",
    r"passed out",
    r"passing out",
    r"black(ing|ed)? out",
    r"syncope",
    r"severe dizziness",
    r"sudden dizziness",
    r"severe(ly)? dizzy",
    r"stroke",
    r"face drooping",
    r"sudden (weakness|numbness)",
    r"slurred speech",
    r"trouble speaking",
    r"can('|no)?t speak",
    r"coughing up blood",
    r"coughing up (pink|frothy)",
    r"blue lips",
    r"severe allergic reaction",
    r"anaphylaxis",
    r"suicidal",
    r"kill myself",
    r"should i (go to|call) (the )?(er|emergency|911)",
    r"call 911",
]

_COMPILED = [re.compile(p, re.IGNORECASE) for p in _URGENT_PATTERNS]
_NEGATION_WINDOW = re.compile(
    r"(no|not|without|den(y|ies|ied)|do not have|don't have|does not have|doesn't have)\s+"
    r"(\w+\s+){0,4}$",
    re.IGNORECASE,
)

ESCALATION_MESSAGE = (
    "Your message mentions symptoms that can be a medical emergency. I can't provide "
    "medical advice for this. If you are experiencing severe or sudden symptoms such as "
    "chest pain or pressure, severe shortness of breath, fainting, severe dizziness, "
    "signs of a stroke (face drooping, arm weakness, difficulty speaking), or coughing up "
    "blood, please call your local emergency number (such as 911) or go to the nearest "
    "emergency department now. Do not drive yourself. If you are unsure, it is safest to "
    "seek emergency care."
)


@dataclass
class GuardrailResult:
    triggered: bool
    matched_terms: list[str]
    message: str | None = None
    source: str = "none"
    semantic_risk: str | None = None
    semantic_confidence: float | None = None
    semantic_reason: str | None = None
    semantic_error: str | None = None


@dataclass
class SemanticRiskResult:
    risk: str
    confidence: float
    matched_concepts: list[str]
    reason: str


SEMANTIC_PROMPT_TEMPLATE = """You are a safety classifier for a document-grounded health education assistant.

Classify whether the user's message describes current or imminent emergency/high-risk symptoms that should receive an emergency escalation message instead of normal educational RAG.

Emergency/high-risk examples include chest pain or pressure, severe shortness of breath, fainting, severe dizziness, stroke symptoms, coughing up blood, blue lips, severe allergic reaction/anaphylaxis, suicidal ideation, or explicitly asking whether to call emergency services.

Do not answer the user's medical question. Return only strict JSON with this schema:
{{"risk":"emergency|non_urgent|uncertain","confidence":0.0,"matched_concepts":["short concept"],"reason":"short explanation"}}

Use "emergency" only for likely current or imminent high-risk symptoms. Use "non_urgent" for general education questions. Use "uncertain" when the wording is too ambiguous.

User message:
{question}
"""


def _extract_json_object(text: str) -> dict[str, Any]:
    """Parse a JSON object, allowing a model to wrap it in extra text."""
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")
        if start == -1 or end == -1 or end <= start:
            raise
        parsed = json.loads(text[start : end + 1])
    if not isinstance(parsed, dict):
        raise ValueError("semantic classifier response was not a JSON object")
    return parsed


def _classify_with_ollama(question: str) -> SemanticRiskResult:
    """Call local Ollama and parse the strict JSON risk classification."""
    payload = {
        "model": settings.ollama_risk_model,
        "prompt": SEMANTIC_PROMPT_TEMPLATE.format(question=question),
        "stream": False,
        "format": "json",
        "options": {"temperature": 0},
    }
    data = json.dumps(payload).encode("utf-8")
    url = f"{settings.ollama_base_url.rstrip('/')}/api/generate"
    req = request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with request.urlopen(req, timeout=settings.ollama_timeout_seconds) as resp:
        body = json.loads(resp.read().decode("utf-8"))

    raw_response = body.get("response")
    if not isinstance(raw_response, str) or not raw_response.strip():
        raise ValueError("Ollama response did not include a response string")

    parsed = _extract_json_object(raw_response)
    risk = str(parsed.get("risk", "")).strip().lower()
    if risk not in {"emergency", "non_urgent", "uncertain"}:
        raise ValueError(f"invalid semantic risk value: {risk!r}")

    confidence = float(parsed.get("confidence", 0.0))
    confidence = max(0.0, min(1.0, confidence))
    concepts = parsed.get("matched_concepts", [])
    if not isinstance(concepts, list):
        concepts = []
    matched_concepts = [str(c) for c in concepts if str(c).strip()]
    reason = str(parsed.get("reason", "")).strip()
    return SemanticRiskResult(
        risk=risk,
        confidence=confidence,
        matched_concepts=matched_concepts,
        reason=reason,
    )


def check_guardrails(question: str) -> GuardrailResult:
    matched = []
    for c in _COMPILED:
        for match in c.finditer(question):
            prefix = question[max(0, match.start() - 60) : match.start()]
            if _NEGATION_WINDOW.search(prefix):
                continue
            matched.append(c.pattern)
            break
    if matched:
        return GuardrailResult(
            triggered=True,
            matched_terms=matched,
            message=ESCALATION_MESSAGE,
            source="regex",
        )

    if not settings.semantic_guardrail_enabled:
        return GuardrailResult(triggered=False, matched_terms=[], source="none")

    try:
        semantic = _classify_with_ollama(question)
    except (
        OSError,
        TimeoutError,
        ValueError,
        json.JSONDecodeError,
        error.URLError,
        error.HTTPError,
    ) as exc:
        return GuardrailResult(
            triggered=False,
            matched_terms=[],
            source="none",
            semantic_error=f"{type(exc).__name__}: {exc}",
        )

    should_escalate = (
        semantic.risk == "emergency"
        and semantic.confidence >= settings.semantic_risk_threshold
    )
    return GuardrailResult(
        triggered=should_escalate,
        matched_terms=semantic.matched_concepts,
        message=ESCALATION_MESSAGE if should_escalate else None,
        source="semantic" if should_escalate else "none",
        semantic_risk=semantic.risk,
        semantic_confidence=round(semantic.confidence, 4),
        semantic_reason=semantic.reason,
    )
