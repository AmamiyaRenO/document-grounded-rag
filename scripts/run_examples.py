"""Run the five required example questions and print request/response pairs.

Forces the deterministic (no-API-key) generation path so the output is reproducible,
and writes real records to logs/research_log.jsonl. Run from the project root:

    uv run python scripts/run_examples.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from hfpef_rag import config  # noqa: E402

config.settings.openai_api_key = None  # reproducible deterministic answers

from fastapi.testclient import TestClient  # noqa: E402

from hfpef_rag.app import app  # noqa: E402

CASES = [
    ("General HFpEF education", "What is HFpEF?"),
    ("Treatment-related", "What should I ask my doctor about HFpEF treatment options?"),
    ("Insufficient evidence", "What are the symptoms of appendicitis?"),
    ("High-risk symptom", "I have severe chest pain and can't breathe, what should I do?"),
    ("Vague / ambiguous", "What about my heart?"),
]


def main() -> None:
    with TestClient(app) as client:
        for label, question in CASES:
            resp = client.post("/ask", json={"question": question})
            print(f"## {label}")
            print("**Request**")
            print("```json")
            print(json.dumps({"question": question}, indent=2))
            print("```")
            print("**Response**")
            print("```json")
            print(json.dumps(resp.json(), indent=2, ensure_ascii=False))
            print("```\n")


if __name__ == "__main__":
    main()
