"""Shared test fixtures.

Tests run fully offline: we force the deterministic generation path (no OpenAI calls,
no cost, reproducible output) and redirect the research log to a temp file so the real
``logs/`` directory is never touched.
"""

from __future__ import annotations

import pytest

from hfpef_rag import config, logging_store


@pytest.fixture(autouse=True)
def offline_and_isolated_logs(tmp_path, monkeypatch):
    # Force the deterministic fallback regardless of any local .env / API key.
    monkeypatch.setattr(config.settings, "openai_api_key", None)
    # Isolate research-log writes to a per-test temp file.
    monkeypatch.setattr(logging_store, "LOG_DIR", tmp_path)
    monkeypatch.setattr(logging_store, "LOG_FILE", tmp_path / "research_log.jsonl")
    yield
