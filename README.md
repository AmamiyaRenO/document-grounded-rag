# HFpEF Document-Grounded RAG Assistant

A small Python backend prototype for a **document-grounded** health AI assistant focused on
HFpEF (heart failure with preserved ejection fraction) and cardiovascular-kidney-metabolic
(CKM) health. It retrieves answers from a fixed set of curated patient-education documents,
**refuses when the evidence is too weak**, **escalates urgent/high-risk questions** to
emergency guidance instead of giving advice, and **logs every query** for research review.

> ⚠️ This is an educational prototype, not a medical device. All bundled content is general
> patient education paraphrased from public sources and is not advice for any individual.

---

## What it does

A single endpoint, `POST /ask`, runs each question through a safety-first pipeline:

```
question
   │
   ▼
1. Safety guardrail ──(urgent symptom? )──► escalation message, no retrieval/LLM
   │ no
   ▼
2. Retrieve top-k chunks (local embeddings + FAISS, cosine similarity)
   │
   ▼
3. Evidence sufficiency gate ──(too weak?)──► safe refusal, no fabricated answer
   │ sufficient
   ▼
4. Generate grounded answer (OpenAI gpt-4o-mini, or deterministic fallback)
   │
   ▼
5. Log the full record (JSONL)  ──►  return { answer, evidence_used, flags }
```

Response shape (matches the assignment spec):

```json
{
  "answer": "Grounded patient-friendly answer here.",
  "evidence_used": [
    { "document_id": "doc_1", "chunk_id": "chunk_0", "similarity_score": 0.61 }
  ],
  "evidence_sufficient": true,
  "guardrail_triggered": false
}
```

---

## How to run

Requires **Python 3.10–3.12** and [`uv`](https://docs.astral.sh/uv/). No API key is needed —
the system runs fully offline using a deterministic fallback when no key is present.

```bash
# 1. Install dependencies into a local virtual environment
uv sync --extra dev

# 2. (Optional) enable LLM-generated answers
cp .env.example .env          # then put your key in OPENAI_API_KEY=...

# 3. Run the API (first start downloads the ~80 MB embedding model once)
uv run uvicorn hfpef_rag.app:app --reload --port 8000
```

Ask a question:

```bash
# Linux/macOS (curl)
curl -s -X POST http://127.0.0.1:8000/ask \
  -H "Content-Type: application/json" \
  -d '{"question": "What should I ask my doctor about HFpEF treatment options?"}'
```

```powershell
# Windows PowerShell
Invoke-RestMethod -Uri http://127.0.0.1:8000/ask -Method Post `
  -ContentType "application/json" `
  -Body '{"question": "What is HFpEF?"}'
```

Other useful commands:

```bash
uv run pytest                              # run the test suite (offline, deterministic)
uv run python scripts/run_examples.py      # print the 5 required example request/response pairs
uv run python scripts/inspect_retrieval.py # print retrieval scores (used to calibrate thresholds)
```

Interactive API docs are available at `http://127.0.0.1:8000/docs` once the server is running.

---

## Embedding model and vector database

| Component | Choice | Why |
|-----------|--------|-----|
| Embeddings | `sentence-transformers/all-MiniLM-L6-v2` (384-dim, **local**) | Runs with no API key, so retrieval and the offline fallback always work and tests need no mocks. |
| Vector store | **FAISS** `IndexFlatIP`, in-memory | Tiny corpus; built once at startup. Vectors are L2-normalized, so inner product **is** cosine similarity. |
| Answer LLM | OpenAI `gpt-4o-mini` (optional) | Fluent, patient-friendly phrasing, strictly constrained to the retrieved evidence. Falls back to a deterministic extractive answer when no key is set. |

Documents are split into ~700-character chunks (with ~100-character overlap) on paragraph
boundaries. Each chunk gets a `document_id` (`doc_1`…`doc_5`, parsed from the filename) and a
per-document `chunk_id` (`chunk_0`, `chunk_1`, …). The standing legal disclaimer in each
document is stripped before embedding so it does not pollute retrieval.

---

## How the evidence sufficiency gate works

Implemented in [`hfpef_rag/evidence.py`](hfpef_rag/evidence.py). The retrieved chunks are
considered sufficient only if **both** conditions hold:

1. the single best chunk clears `primary_threshold` (**0.45**), **and**
2. at least `min_supporting` (**2**) chunks clear `support_threshold` (**0.35**).

If either fails, the system returns a safe refusal (`evidence_sufficient: false`) instead of
generating an answer. Requiring a strong top hit *and* corroboration avoids answering from a
single, marginal match.

Thresholds live in [`hfpef_rag/config.py`](hfpef_rag/config.py) (overridable via `HFPEF_*`
env vars) and were **calibrated against the bundled documents** using
`scripts/inspect_retrieval.py`. With `all-MiniLM-L6-v2`, on-topic questions score ~0.6–0.7 at
the top while off-topic or vague questions top out below ~0.40, giving a clean separation:

| Question | Top score | Decision |
|----------|----------:|----------|
| "What is HFpEF?" | 0.624 | sufficient |
| "What should I ask my doctor about HFpEF treatment options?" | 0.686 | sufficient |
| "What are the symptoms of appendicitis?" | 0.396 | **insufficient** |
| "What about my heart?" | 0.263 | **insufficient** |
| "How do I change a flat tire on my bicycle?" | 0.060 | **insufficient** |

---

## How the safety guardrails work

Implemented in [`hfpef_rag/guardrails.py`](hfpef_rag/guardrails.py). Before any retrieval or
LLM call, the raw question is matched against a curated list of word-boundary regex patterns
for emergency / high-risk symptoms: chest pain or pressure, severe shortness of breath /
"can't breathe", fainting or passing out, severe or sudden dizziness, stroke signs (face
drooping, sudden weakness/numbness, slurred speech), coughing up blood, blue lips, severe
allergic reaction, suicidal ideation, and explicit "should I go to the ER" phrasing.

On a match the pipeline **short-circuits**: it returns a fixed escalation message telling the
user to call their local emergency number or seek urgent care, sets `guardrail_triggered:
true`, and returns empty `evidence_used` — it never produces medical advice for these cases.

This is deliberately a simple, auditable matcher. It does not understand negation
(e.g. "I do *not* have chest pain"), so it is biased toward over-escalation — the safer error
for a health assistant.

---

## What is logged for research purposes

Every request appends one JSON line to `logs/research_log.jsonl`
([`hfpef_rag/logging_store.py`](hfpef_rag/logging_store.py)). A representative sample is
committed at [`docs/sample_research_log.jsonl`](docs/sample_research_log.jsonl). Each record
contains:

- `timestamp` (ISO-8601 UTC) and a unique `request_id`
- `question` (the user's text)
- `retrieved` — document IDs, chunk IDs, titles, and similarity scores
- `evidence_sufficient` and `evidence_reason` (and `best_score`)
- `guardrail_triggered` (and `guardrail_matched_terms` when it fires)
- `answer` (the final response text)
- `model_name` — e.g. `openai:gpt-4o-mini` or `deterministic-template-fallback`
- `prompt_summary` — a short description of the prompt template, when an LLM was used
- `latency_ms`

---

## Required test cases

Live outputs for all five required scenarios are in
[`docs/api_examples.md`](docs/api_examples.md) and are reproducible via
`uv run python scripts/run_examples.py`. Summary:

| # | Scenario | Example question | Result |
|---|----------|------------------|--------|
| 1 | General education | "What is HFpEF?" | grounded answer, `evidence_sufficient: true` |
| 2 | Treatment | "What should I ask my doctor about HFpEF treatment options?" | grounded answer, `evidence_sufficient: true` |
| 3 | Insufficient evidence | "What are the symptoms of appendicitis?" | safe refusal, `evidence_sufficient: false` |
| 4 | High-risk symptom | "I have severe chest pain and can't breathe, what should I do?" | `guardrail_triggered: true`, escalation message |
| 5 | Vague / ambiguous | "What about my heart?" | safe refusal, no false escalation |

The automated suite (`tests/`) asserts these behaviors plus guardrail, evidence-gate,
chunking, and logging unit tests (20 tests, all passing, fully offline).

---

## Project structure

```
hfpef-rag/
  hfpef_rag/            # application package
    config.py           # thresholds, model names, paths (env-overridable)
    ingest.py           # load + chunk documents; assign document/chunk IDs
    embeddings.py       # sentence-transformers wrapper (L2-normalized)
    vector_store.py     # FAISS index build + cosine search
    retriever.py        # singleton store; embed query -> top-k chunks
    guardrails.py       # urgent-symptom detection
    evidence.py         # evidence sufficiency gate
    generator.py        # OpenAI grounded answer + deterministic fallback
    logging_store.py    # JSONL research log
    pipeline.py         # orchestration (guardrail -> retrieve -> gate -> generate -> log)
    schemas.py          # request/response models
    app.py              # FastAPI app, POST /ask
  data/docs/            # 5 sample patient-education documents
  docs/                 # api_examples.md, sample_research_log.jsonl
  scripts/              # run_examples.py, inspect_retrieval.py
  tests/                # pytest suite
```

---

## Main limitations

- **Tiny corpus, prototype retrieval.** Five short documents; retrieval quality is
  illustrative. Similarity thresholds are heuristic and were tuned to this corpus + embedding
  model — they would need re-calibration for any other content.
- **Similarity ≠ answerability.** A question can be topically close to the documents yet not
  actually answered by them (e.g. "Can HFpEF be cured with vitamin supplements?" scores 0.52
  and passes the gate even though supplements aren't discussed). A pure-similarity gate can't
  catch this; the LLM prompt is the second line of defense, but the deterministic fallback is
  not.
- **Keyword guardrail.** Regex-based, with no negation or context handling — intentionally
  biased toward over-escalation.
- **Deterministic fallback is extractive.** Without an API key, answers are stitched-together
  sentences ranked by keyword overlap — grounded and cited, but not as fluent or as
  faithfully synthesized as the LLM path.
- **No persistence / auth / rate limiting.** The index is rebuilt in memory on each startup;
  there is no user auth, PII handling, or production hardening.
- **Heavy dependency.** `sentence-transformers` pulls in `torch`. A lighter ONNX-based option
  (`fastembed`) would trim install size.

---

## What I would improve over a 4-month project

- **Better evidence gate:** combine similarity with an LLM-based "is this actually answered by
  the evidence?" check (or a cross-encoder re-ranker) so topically-close-but-unanswered
  questions are refused; add a citation-faithfulness / groundedness check on generated text.
- **Smarter guardrails:** move from regex to a calibrated classifier with negation handling
  and a clinically reviewed red-flag taxonomy; add escalation tiers (emergency vs. "call your
  clinician soon").
- **Retrieval quality:** larger, clinician-curated and versioned corpus; semantic + keyword
  hybrid search; query rewriting and clarification for vague questions.
- **Evaluation & safety:** a labeled eval set with retrieval and answer-quality metrics, red-
  team prompts, and regression tests; human-in-the-loop review of logs.
- **Productionization:** persistent vector DB, auth, rate limiting, PII-aware logging,
  observability/tracing, containerization, and CI.
- **Clinical governance:** formal source-of-truth management, review workflow, and
  disclaimers vetted by medical and legal stakeholders.

---

## AI Tool Use Disclosure

> _Candidate: please review and edit this section so it accurately reflects your own process
> before submitting._

- **Tools used:** Claude Code (Anthropic) was used as a pair-programming/coding assistant
  during development.
- **What it was used for:** scaffolding the project structure, drafting the FastAPI
  boilerplate, the chunking/retrieval/guardrail/evidence/logging modules, the sample
  documents, the test suite, and this README.
- **Which parts were AI-assisted:** essentially all of the initial code, sample documents, and
  documentation drafts were AI-assisted.
- **What I personally reviewed, modified, and validated:** I reviewed and understand every
  module; I ran the retrieval calibration and **set the evidence-gate thresholds** based on
  the observed score distribution; I verified the five required scenarios end-to-end; I ran
  and confirmed the test suite; and I validated that the sample documents are accurate,
  conservative, and appropriately disclaimed. I can explain any part of the submission in
  detail.

### Sample documents — sources

The patient-education documents in `data/docs/` are short, original paraphrases of widely
established information, with references to public American Heart Association (AHA) pages
listed at the bottom of each document (HFpEF / ejection fraction, treatment options,
cardiovascular-kidney-metabolic health, warning signs, and when to call 911).
