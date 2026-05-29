"""Safety guardrail: detect urgent / high-risk queries.

This runs *before* retrieval and generation. If the question matches a red-flag
pattern, the system returns a fixed escalation message and gives no medical advice.

Design note / limitation: this is intentionally a simple, auditable keyword/regex
matcher. It does not understand negation ("I do NOT have chest pain") or nuanced
context. For a safety gate we accept that bias toward over-escalation.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# Each pattern is matched case-insensitively with word boundaries where appropriate.
# Patterns target the emergency symptoms named in the task plus common red flags.
_URGENT_PATTERNS: list[str] = [
    r"chest pain",
    r"chest pressure",
    r"chest tightness",
    r"chest discomfort",
    r"pressure in (my )?chest",
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


def check_guardrails(question: str) -> GuardrailResult:
    matched = [c.pattern for c in _COMPILED if c.search(question)]
    if matched:
        return GuardrailResult(
            triggered=True, matched_terms=matched, message=ESCALATION_MESSAGE
        )
    return GuardrailResult(triggered=False, matched_terms=[])
