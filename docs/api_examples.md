# Example API Requests and Responses

All examples below were produced by the **deterministic (no-API-key) generation path**,
so they are reproducible by anyone running the prototype without an `OPENAI_API_KEY`.
When a key is configured, the `answer` text is instead written by the LLM
(`openai:gpt-4o-mini`) using the same retrieved evidence; the `evidence_used`,
`evidence_sufficient`, and `guardrail_triggered` fields are unchanged.

Regenerate these with: `uv run python scripts/run_examples.py`

---

## 1. General HFpEF education

**Request**
```json
{ "question": "What is HFpEF?" }
```
**Response**
```json
{
  "answer": "Here is what my reference documents say that relates to your question:\n\n- Treatment Options for HFpEF General goals of treatment The main goals in HFpEF are to relieve symptoms, reduce fluid buildup, prevent hospitalizations, and treat the conditions that contribute to it (such as high blood pressure, diabetes, obesity, kidney disease, and atrial fibrillation). [doc_2/chunk_0]\n- Because HFpEF is closely tied to these other conditions, managing them well is a central part of care. [doc_2/chunk_0]\n- HFpEF: An Overview for Patients What is HFpEF? [doc_1/chunk_0]\n- Heart failure with preserved ejection fraction (HFpEF) is a type of heart failure in which the heart's main pumping chamber (the left ventricle) squeezes normally but has become stiff and does not relax or fill with blood as easily as it should. [doc_1/chunk_0]\n- In HFpEF the ejection fraction is preserved, usually 50% or higher, even though the heart is not working normally. [doc_1/chunk_0]\n\n_This is general health education based on reference documents, not medical advice. Please talk with your own clinician about your situation._",
  "evidence_used": [
    { "document_id": "doc_2", "chunk_id": "chunk_0", "similarity_score": 0.6242 },
    { "document_id": "doc_1", "chunk_id": "chunk_0", "similarity_score": 0.6088 },
    { "document_id": "doc_1", "chunk_id": "chunk_2", "similarity_score": 0.4939 },
    { "document_id": "doc_1", "chunk_id": "chunk_3", "similarity_score": 0.4899 },
    { "document_id": "doc_1", "chunk_id": "chunk_1", "similarity_score": 0.4598 }
  ],
  "evidence_sufficient": true,
  "guardrail_triggered": false
}
```

---

## 2. Treatment-related

**Request**
```json
{ "question": "What should I ask my doctor about HFpEF treatment options?" }
```
**Response**
```json
{
  "answer": "Here is what my reference documents say that relates to your question:\n\n- Treatment Options for HFpEF General goals of treatment The main goals in HFpEF are to relieve symptoms, reduce fluid buildup, prevent hospitalizations, and treat the conditions that contribute to it (such as high blood pressure, diabetes, obesity, kidney disease, and atrial fibrillation). [doc_2/chunk_0]\n- Because HFpEF is closely tied to these other conditions, managing them well is a central part of care. [doc_2/chunk_0]\n- Questions to Ask Your Doctor About HFpEF Understanding your condition - What is my ejection fraction, and what does that number mean for me? [doc_5/chunk_0]\n- - What is causing or contributing to my HFpEF (for example, blood pressure, diabetes, or kidney disease)? [doc_5/chunk_0]\n- Questions about treatment options [doc_5/chunk_0]\n\n_This is general health education based on reference documents, not medical advice. Please talk with your own clinician about your situation._",
  "evidence_used": [
    { "document_id": "doc_2", "chunk_id": "chunk_0", "similarity_score": 0.6862 },
    { "document_id": "doc_5", "chunk_id": "chunk_0", "similarity_score": 0.623 },
    { "document_id": "doc_5", "chunk_id": "chunk_2", "similarity_score": 0.5911 },
    { "document_id": "doc_1", "chunk_id": "chunk_2", "similarity_score": 0.5498 },
    { "document_id": "doc_2", "chunk_id": "chunk_1", "similarity_score": 0.5027 }
  ],
  "evidence_sufficient": true,
  "guardrail_triggered": false
}
```

---

## 3. Question with insufficient evidence

`appendicitis` is a health topic, but it is **not** covered by the bundled documents.
The best chunk scores 0.396, below the `primary_threshold` of 0.45, so the system refuses
instead of guessing.

**Request**
```json
{ "question": "What are the symptoms of appendicitis?" }
```
**Response**
```json
{
  "answer": "I don't have enough information in my reference documents to answer that reliably, so I'd rather not guess. The documents I can draw on cover HFpEF basics, treatment options, cardiovascular-kidney-metabolic health, warning signs, and questions to ask your doctor. You could try rephrasing your question around one of those topics, or ask your clinician or pharmacist, who can give advice specific to you.",
  "evidence_used": [
    { "document_id": "doc_4", "chunk_id": "chunk_1", "similarity_score": 0.3958 },
    { "document_id": "doc_4", "chunk_id": "chunk_0", "similarity_score": 0.3726 },
    { "document_id": "doc_4", "chunk_id": "chunk_2", "similarity_score": 0.2057 },
    { "document_id": "doc_1", "chunk_id": "chunk_2", "similarity_score": 0.2028 },
    { "document_id": "doc_5", "chunk_id": "chunk_3", "similarity_score": 0.1507 }
  ],
  "evidence_sufficient": false,
  "guardrail_triggered": false
}
```

---

## 4. High-risk symptom (safety guardrail)

The guardrail matches before any retrieval or LLM call, so `evidence_used` is empty and
no medical advice is generated.

**Request**
```json
{ "question": "I have severe chest pain and can't breathe, what should I do?" }
```
**Response**
```json
{
  "answer": "Your message mentions symptoms that can be a medical emergency. I can't provide medical advice for this. If you are experiencing severe or sudden symptoms such as chest pain or pressure, severe shortness of breath, fainting, severe dizziness, signs of a stroke (face drooping, arm weakness, difficulty speaking), or coughing up blood, please call your local emergency number (such as 911) or go to the nearest emergency department now. Do not drive yourself. If you are unsure, it is safest to seek emergency care.",
  "evidence_used": [],
  "evidence_sufficient": false,
  "guardrail_triggered": true
}
```

---

## 5. Vague / ambiguous question

A vague question does not falsely trigger the safety guardrail; it simply fails the
evidence gate (top score 0.263) and is refused with a request to be more specific.

**Request**
```json
{ "question": "What about my heart?" }
```
**Response**
```json
{
  "answer": "I don't have enough information in my reference documents to answer that reliably, so I'd rather not guess. The documents I can draw on cover HFpEF basics, treatment options, cardiovascular-kidney-metabolic health, warning signs, and questions to ask your doctor. You could try rephrasing your question around one of those topics, or ask your clinician or pharmacist, who can give advice specific to you.",
  "evidence_used": [
    { "document_id": "doc_5", "chunk_id": "chunk_1", "similarity_score": 0.2633 },
    { "document_id": "doc_4", "chunk_id": "chunk_0", "similarity_score": 0.2516 },
    { "document_id": "doc_1", "chunk_id": "chunk_1", "similarity_score": 0.2412 },
    { "document_id": "doc_1", "chunk_id": "chunk_4", "similarity_score": 0.2346 },
    { "document_id": "doc_3", "chunk_id": "chunk_3", "similarity_score": 0.2214 }
  ],
  "evidence_sufficient": false,
  "guardrail_triggered": false
}
```
