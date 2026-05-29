"""Append-only research logging.

Every query writes one JSON object (one line) to ``logs/research_log.jsonl`` capturing
everything needed to audit a response: what was retrieved, the gate and guardrail
decisions, the final answer, and the model / prompt details when an LLM was used.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from .config import LOG_DIR, LOG_FILE


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def write_log(record: dict[str, Any]) -> dict[str, Any]:
    """Append ``record`` (with a UTC timestamp) as one JSON line. Returns the record."""
    record = {"timestamp": _utc_now_iso(), **record}
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    with LOG_FILE.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, ensure_ascii=False) + "\n")
    return record
