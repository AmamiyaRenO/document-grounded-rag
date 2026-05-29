"""Guardrail unit tests: urgent symptoms escalate; ordinary questions do not."""

import pytest

from hfpef_rag import config, guardrails
from hfpef_rag.guardrails import (
    ESCALATION_MESSAGE,
    SemanticRiskResult,
    check_guardrails,
)

URGENT = [
    "I have severe chest pain and can't breathe, what should I do?",
    "My father just fainted and is unresponsive",
    "I'm having sudden weakness on one side and slurred speech",
    "I feel severe dizziness and chest pressure",
    "Should I go to the ER?",
    "My chest feels crushed and I'm sweating.",
]

NON_URGENT = [
    "What is HFpEF?",
    "What should I ask my doctor about HFpEF treatment options?",
    "How does a low-sodium diet help with heart failure?",
    "What is cardiovascular-kidney-metabolic syndrome?",
    "I do not have chest pain. What symptoms should I watch for?",
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


def test_regex_hard_gate_runs_before_semantic_classifier(monkeypatch):
    monkeypatch.setattr(config.settings, "semantic_guardrail_enabled", True)

    def fail_if_called(question):  # pragma: no cover - should never run
        raise AssertionError("semantic classifier should not run after regex match")

    monkeypatch.setattr(guardrails, "_classify_with_ollama", fail_if_called)

    result = check_guardrails("I have severe chest pain and can't breathe")

    assert result.triggered is True
    assert result.source == "regex"
    assert result.message == ESCALATION_MESSAGE


def test_semantic_classifier_can_trigger_for_emergency_paraphrase(monkeypatch):
    monkeypatch.setattr(config.settings, "semantic_guardrail_enabled", True)
    monkeypatch.setattr(config.settings, "semantic_risk_threshold", 0.75)

    def classify(question):
        return SemanticRiskResult(
            risk="emergency",
            confidence=0.92,
            matched_concepts=["crushing chest pressure"],
            reason="Possible current cardiac emergency symptom.",
        )

    monkeypatch.setattr(guardrails, "_classify_with_ollama", classify)

    result = check_guardrails("It feels like an elephant is sitting on my chest.")

    assert result.triggered is True
    assert result.source == "semantic"
    assert result.matched_terms == ["crushing chest pressure"]
    assert result.semantic_risk == "emergency"
    assert result.semantic_confidence == 0.92
    assert result.message == ESCALATION_MESSAGE


def test_semantic_non_urgent_question_does_not_trigger(monkeypatch):
    monkeypatch.setattr(config.settings, "semantic_guardrail_enabled", True)

    def classify(question):
        return SemanticRiskResult(
            risk="non_urgent",
            confidence=0.91,
            matched_concepts=[],
            reason="General education question.",
        )

    monkeypatch.setattr(guardrails, "_classify_with_ollama", classify)

    result = check_guardrails("What warning signs should HFpEF patients know?")

    assert result.triggered is False
    assert result.source == "none"
    assert result.semantic_risk == "non_urgent"
    assert result.semantic_confidence == 0.91


def test_semantic_uncertain_question_does_not_trigger(monkeypatch):
    monkeypatch.setattr(config.settings, "semantic_guardrail_enabled", True)

    def classify(question):
        return SemanticRiskResult(
            risk="uncertain",
            confidence=0.88,
            matched_concepts=["ambiguous symptom"],
            reason="Too ambiguous to classify as emergency.",
        )

    monkeypatch.setattr(guardrails, "_classify_with_ollama", classify)

    result = check_guardrails("Something feels weird.")

    assert result.triggered is False
    assert result.source == "none"
    assert result.semantic_risk == "uncertain"


def test_semantic_low_confidence_emergency_does_not_trigger(monkeypatch):
    monkeypatch.setattr(config.settings, "semantic_guardrail_enabled", True)
    monkeypatch.setattr(config.settings, "semantic_risk_threshold", 0.75)

    def classify(question):
        return SemanticRiskResult(
            risk="emergency",
            confidence=0.4,
            matched_concepts=["possible symptom"],
            reason="Low confidence.",
        )

    monkeypatch.setattr(guardrails, "_classify_with_ollama", classify)

    result = check_guardrails("I felt odd earlier.")

    assert result.triggered is False
    assert result.source == "none"
    assert result.semantic_risk == "emergency"
    assert result.semantic_confidence == 0.4


def test_semantic_classifier_error_fails_open(monkeypatch):
    monkeypatch.setattr(config.settings, "semantic_guardrail_enabled", True)

    def classify(question):
        raise TimeoutError("Ollama timed out")

    monkeypatch.setattr(guardrails, "_classify_with_ollama", classify)

    result = check_guardrails("I feel unusual today.")

    assert result.triggered is False
    assert result.source == "none"
    assert "TimeoutError" in result.semantic_error


def test_semantic_prompt_formats_with_json_schema():
    prompt = guardrails.SEMANTIC_PROMPT_TEMPLATE.format(question="test question")

    assert '"risk":"emergency|non_urgent|uncertain"' in prompt
    assert "test question" in prompt
