"""FastAPI application exposing ``POST /ask``.

The vector index (and embedding model) are built once on startup so the first request
isn't penalized with the model-load cost.
"""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI

from .config import settings
from .pipeline import answer_question
from .retriever import warmup
from .schemas import AskRequest, AskResponse


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Build the index / load the embedding model before serving traffic.
    warmup()
    yield


app = FastAPI(
    title="HFpEF Document-Grounded RAG Assistant",
    description=(
        "A document-grounded patient-education prototype with an evidence-sufficiency "
        "gate, safety guardrails, and research logging."
    ),
    version="0.1.0",
    lifespan=lifespan,
)


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "llm_enabled": settings.llm_enabled, "llm_model": settings.llm_model}


@app.post("/ask", response_model=AskResponse)
def ask(request: AskRequest) -> AskResponse:
    return answer_question(request.question)
