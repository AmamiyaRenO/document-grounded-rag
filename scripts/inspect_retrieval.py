"""Dev helper: print retrieval scores for a set of probe questions.

Useful for calibrating the evidence-gate thresholds in ``config.py`` against the
bundled documents. Run with:  uv run python scripts/inspect_retrieval.py
"""

from __future__ import annotations

import sys
from pathlib import Path

# Make the project root importable when run as a standalone script.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from hfpef_rag.config import settings  # noqa: E402
from hfpef_rag.retriever import retrieve  # noqa: E402

PROBES = [
    "What is HFpEF?",
    "What should I ask my doctor about HFpEF treatment options?",
    "Can HFpEF be cured by taking vitamin supplements?",
    "What are the symptoms of appendicitis?",
    "How do I change a flat tire on my bicycle?",
    "Is it serious?",
    "What about my heart?",
]


def main() -> None:
    print(
        f"thresholds: primary={settings.primary_threshold} "
        f"support={settings.support_threshold} min_supporting={settings.min_supporting}\n"
    )
    for q in PROBES:
        results = retrieve(q)
        top = results[0].similarity_score if results else 0.0
        print(f"Q: {q}\n   top={top:.3f}")
        for r in results:
            print(
                f"     {r.chunk.document_id}/{r.chunk.chunk_id}  "
                f"{r.similarity_score:.3f}  {r.chunk.title}"
            )
        print()


if __name__ == "__main__":
    main()
