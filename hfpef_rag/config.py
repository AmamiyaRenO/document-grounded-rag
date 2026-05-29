"""Central configuration.

All tunable knobs live here so the evidence gate, embedding model, and LLM settings
are documented in one place and overridable via environment variables (prefix ``HFPEF_``)
or a local ``.env`` file. See ``.env.example``.
"""

from __future__ import annotations

from pathlib import Path

from dotenv import load_dotenv
from pydantic_settings import BaseSettings, SettingsConfigDict

# Project paths (resolved relative to this file, so the app works from any CWD).
PACKAGE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = PACKAGE_DIR.parent
DOCS_DIR = PROJECT_ROOT / "data" / "docs"
LOG_DIR = PROJECT_ROOT / "logs"
LOG_FILE = LOG_DIR / "research_log.jsonl"

# Load .env into the process environment so both the unprefixed OPENAI_API_KEY
# and the HFPEF_-prefixed overrides are visible to pydantic-settings and the
# OpenAI SDK alike.
load_dotenv(PROJECT_ROOT / ".env")


class Settings(BaseSettings):
    """Runtime settings. Env vars use the ``HFPEF_`` prefix (e.g. ``HFPEF_TOP_K``)."""

    model_config = SettingsConfigDict(
        env_prefix="HFPEF_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- Retrieval / embeddings -------------------------------------------------
    embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2"
    top_k: int = 5
    chunk_size_chars: int = 700
    chunk_overlap_chars: int = 100

    # --- Evidence sufficiency gate ----------------------------------------------
    # Cosine similarity is in [-1, 1]. Calibrated on the bundled docs with
    # all-MiniLM-L6-v2: on-topic questions score ~0.6-0.7 at the top with several
    # corroborating chunks >= 0.35, while off-topic/vague questions top out below
    # ~0.40. The gate requires BOTH a strong best chunk AND corroboration.
    primary_threshold: float = 0.45  # the single best chunk must clear this
    support_threshold: float = 0.35  # chunks counted as "supporting"
    min_supporting: int = 2  # how many supporting chunks are required

    # --- Answer generation (LLM) ------------------------------------------------
    # When OPENAI_API_KEY is set, answers are generated with this model; otherwise
    # the system falls back to a deterministic extractive/template answer.
    openai_api_key: str | None = None
    llm_model: str = "gpt-4o-mini"
    llm_temperature: float = 0.2
    llm_max_tokens: int = 500

    # --- Optional evidence answerability check ---------------------------------
    # Runs after the similarity gate passes and before answer generation. It asks
    # whether the retrieved evidence actually answers the user's question, since
    # topical similarity is not the same as answerability.
    answerability_check_enabled: bool = True
    answerability_model: str | None = None
    answerability_temperature: float = 0.0
    answerability_max_tokens: int = 250

    # --- Safety guardrail semantic classifier ---------------------------------
    # Regex remains the deterministic hard gate. When enabled, this optional
    # offline classifier runs only after regex does not match, and fails open if
    # Ollama is unavailable or returns malformed output.
    semantic_guardrail_enabled: bool = True
    ollama_base_url: str = "http://127.0.0.1:11434"
    ollama_risk_model: str = "qwen3:8b"
    ollama_timeout_seconds: float = 8.0
    semantic_risk_threshold: float = 0.75

    @property
    def llm_enabled(self) -> bool:
        return bool(self.openai_api_key)


# OPENAI_API_KEY is conventionally unprefixed, so read it explicitly as a fallback.
def _load_settings() -> Settings:
    import os

    settings = Settings()
    if settings.openai_api_key is None:
        settings.openai_api_key = os.environ.get("OPENAI_API_KEY")
    return settings


settings = _load_settings()
