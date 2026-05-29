"""End-to-end API tests covering the five required scenarios.

These exercise the real retriever (the embedding model loads on first use) but force
the deterministic generation path via the autouse fixture in conftest.py, so results
are reproducible and require no API key.
"""

import json

import pytest
from fastapi.testclient import TestClient

from hfpef_rag import answerability, config, guardrails, logging_store
from hfpef_rag.app import app
from hfpef_rag.answerability import AnswerabilityDecision
from hfpef_rag.guardrails import SemanticRiskResult


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


def _ask(client, question: str) -> dict:
    resp = client.post("/ask", json={"question": question})
    assert resp.status_code == 200
    return resp.json()


def _assert_schema(body: dict):
    assert set(body) == {
        "answer",
        "evidence_used",
        "evidence_sufficient",
        "guardrail_triggered",
    }
    assert isinstance(body["answer"], str) and body["answer"]
    for item in body["evidence_used"]:
        assert set(item) == {"document_id", "chunk_id", "similarity_score"}


# 1. General HFpEF education question -------------------------------------------
def test_general_education_is_grounded(client):
    body = _ask(client, "What is HFpEF?")
    _assert_schema(body)
    assert body["guardrail_triggered"] is False
    assert body["evidence_sufficient"] is True
    assert body["evidence_used"]
    assert any(e["document_id"] == "doc_1" for e in body["evidence_used"])


# 2. Treatment-related question -------------------------------------------------
def test_treatment_question_is_grounded(client):
    body = _ask(client, "What should I ask my doctor about HFpEF treatment options?")
    _assert_schema(body)
    assert body["guardrail_triggered"] is False
    assert body["evidence_sufficient"] is True
    assert body["evidence_used"]


# 3. Question with insufficient evidence (clearly off-corpus) -------------------
def test_off_topic_question_is_refused(client):
    body = _ask(client, "How do I change a flat tire on my bicycle?")
    _assert_schema(body)
    assert body["guardrail_triggered"] is False
    assert body["evidence_sufficient"] is False


# 4. High-risk symptom question -------------------------------------------------
def test_high_risk_question_escalates(client):
    body = _ask(client, "I have severe chest pain and can't breathe, what should I do?")
    _assert_schema(body)
    assert body["guardrail_triggered"] is True
    assert body["evidence_sufficient"] is False
    assert body["evidence_used"] == []
    assert "911" in body["answer"] or "emergency" in body["answer"].lower()


# 5. Vague / ambiguous question -------------------------------------------------
def test_vague_question_does_not_falsely_escalate(client):
    body = _ask(client, "Is it serious?")
    _assert_schema(body)
    assert body["guardrail_triggered"] is False


# Research logging ---------------------------------------------------------------
def test_each_query_appends_a_log_record(client):
    before = (
        sum(1 for _ in logging_store.LOG_FILE.open(encoding="utf-8"))
        if logging_store.LOG_FILE.exists()
        else 0
    )
    _ask(client, "What is HFpEF?")
    lines = logging_store.LOG_FILE.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == before + 1

    record = json.loads(lines[-1])
    for key in (
        "timestamp",
        "question",
        "retrieved",
        "evidence_sufficient",
        "guardrail_triggered",
        "guardrail_source",
        "answerability_checked",
        "answerability_sufficient",
        "answerability_reason",
        "answer",
        "model_name",
    ):
        assert key in record


def test_semantic_guardrail_escalates_and_logs_metadata(client, monkeypatch):
    monkeypatch.setattr(config.settings, "semantic_guardrail_enabled", True)
    monkeypatch.setattr(config.settings, "ollama_risk_model", "qwen3:8b")

    def classify(question):
        return SemanticRiskResult(
            risk="emergency",
            confidence=0.93,
            matched_concepts=["crushing chest pressure"],
            reason="Potential current emergency symptom.",
        )

    monkeypatch.setattr(guardrails, "_classify_with_ollama", classify)

    body = _ask(client, "It feels like an elephant is sitting on my chest.")

    _assert_schema(body)
    assert body["guardrail_triggered"] is True
    assert body["evidence_sufficient"] is False
    assert body["evidence_used"] == []

    record = json.loads(logging_store.LOG_FILE.read_text(encoding="utf-8").splitlines()[-1])
    assert record["guardrail_source"] == "semantic"
    assert record["semantic_guardrail_model"] == "qwen3:8b"
    assert record["semantic_guardrail_risk"] == "emergency"
    assert record["semantic_guardrail_confidence"] == 0.93


def test_answerability_allows_answerable_hfpef_question(client, monkeypatch):
    monkeypatch.setattr(config.settings, "answerability_check_enabled", True)

    def assess(question, results):
        assert question == "What is HFpEF?"
        return AnswerabilityDecision(
            checked=True,
            sufficient=True,
            reason="Evidence defines HFpEF directly.",
            model_name="mock-answerability",
            prompt_summary="mock prompt",
        )

    monkeypatch.setattr(answerability, "assess_answerability", assess)
    monkeypatch.setattr("hfpef_rag.pipeline.assess_answerability", assess)

    body = _ask(client, "What is HFpEF?")

    assert body["evidence_sufficient"] is True
    assert body["guardrail_triggered"] is False

    record = json.loads(logging_store.LOG_FILE.read_text(encoding="utf-8").splitlines()[-1])
    assert record["answerability_checked"] is True
    assert record["answerability_sufficient"] is True
    assert record["answerability_reason"] == "Evidence defines HFpEF directly."


def test_answerability_refuses_topically_similar_but_unanswered_question(
    client, monkeypatch
):
    monkeypatch.setattr(config.settings, "answerability_check_enabled", True)

    def assess(question, results):
        assert question == "Can HFpEF be cured with vitamin supplements?"
        return AnswerabilityDecision(
            checked=True,
            sufficient=False,
            reason="Retrieved evidence discusses HFpEF treatment but does not support a cure with vitamin supplements.",
            model_name="mock-answerability",
            prompt_summary="mock prompt",
        )

    monkeypatch.setattr(answerability, "assess_answerability", assess)
    monkeypatch.setattr("hfpef_rag.pipeline.assess_answerability", assess)

    body = _ask(client, "Can HFpEF be cured with vitamin supplements?")

    assert body["guardrail_triggered"] is False
    assert body["evidence_sufficient"] is False
    assert "don't have enough information" in body["answer"]
    assert body["evidence_used"]

    record = json.loads(logging_store.LOG_FILE.read_text(encoding="utf-8").splitlines()[-1])
    assert record["evidence_reason"] == "answerability_gate_failed"
    assert record["answerability_checked"] is True
    assert record["answerability_sufficient"] is False
    assert "vitamin supplements" in record["answerability_reason"]
