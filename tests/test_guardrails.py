"""Guardrail unit tests: urgent symptoms escalate; ordinary questions do not."""

import pytest

from hfpef_rag.guardrails import ESCALATION_MESSAGE, check_guardrails

URGENT = [
    "I have severe chest pain and can't breathe, what should I do?",
    "My father just fainted and is unresponsive",
    "I'm having sudden weakness on one side and slurred speech",
    "I feel severe dizziness and chest pressure",
    "Should I go to the ER?",
]

NON_URGENT = [
    "What is HFpEF?",
    "What should I ask my doctor about HFpEF treatment options?",
    "How does a low-sodium diet help with heart failure?",
    "What is cardiovascular-kidney-metabolic syndrome?",
]


@pytest.mark.parametrize("question", URGENT)
def test_urgent_questions_trigger(question):
    result = check_guardrails(question)
    assert result.triggered is True
    assert result.matched_terms
    assert result.message == ESCALATION_MESSAGE


@pytest.mark.parametrize("question", NON_URGENT)
def test_ordinary_questions_do_not_trigger(question):
    result = check_guardrails(question)
    assert result.triggered is False
    assert result.message is None
