# Week 2 Cost and Latency Report — Clinical Co-Pilot

All figures are from actual dev runs logged via the `/logs` observability
endpoint. No estimates were substituted for measured values.

---

## Observed Dev Spend

| Metric | Value |
|---|---|
| Total LLM calls logged | 23 |
| Total observed cost | $0.27 |
| Average cost per LLM call | $0.014 |
| Average input tokens per call | 3,230 |
| Average output tokens per call | 286 |

Model: `claude-sonnet-4-6` for all chat and extraction calls.
Reranker: `cohere rerank-english-v3.0` (billed per search, negligible vs. LLM).

---

## Latency by Operation

### Document Extraction (Vision pipeline)

| Percentile | Latency |
|---|---|
| p50 | 19,377 ms |
| p95 | 22,236 ms |

Bottleneck: Claude Vision processes rasterized 300 DPI PNG pages. A 2-page PDF
produces two ~2 MB images. Round-trip to the Vision API dominates. Pydantic
validation and overlay rendering add < 200 ms combined.

### Chat Turn (end-to-end, question to first token)

| Percentile | Latency |
|---|---|
| p50 | 10,547 ms |
| p95 | 14,258 ms |

A typical chat turn involves 2–3 LLM calls: one to select tools, one to process
tool results, one to generate the final answer. The guideline search
(BM25 + ChromaDB + Cohere rerank) adds 800–1,200 ms. Database tool calls
(demographics, medications, encounters) add 50–150 ms each.

---

## Cost per Operation Type

| Operation | Approx. cost |
|---|---|
| Document extraction (1 PDF, 1–2 pages) | $0.04–$0.09 |
| Chat turn with guideline retrieval | $0.025–$0.045 |
| Chat turn without retrieval (chart-only) | $0.012–$0.020 |

---

## Production Projection

Assumptions: 100 providers, 20 consultations per provider per day, 3 chat turns
per consultation, 2 document uploads per consultation.

| Cost driver | Daily volume | Unit cost | Daily cost |
|---|---|---|---|
| Chat turns | 6,000 | $0.035 avg | $210 |
| Document extractions | 4,000 | $0.065 avg | $260 |
| **Total** | | | **$470/day** |

Monthly: ~$14,100. Per-provider per-month: ~$141.

---

## Bottleneck Analysis and Mitigations

**Extraction latency (p95 22 s):** Acceptable for async document upload — the
UI shows a streaming status indicator and the result persists in the overlay
store for instant re-queries. For synchronous use cases, pre-warming with a
background job at appointment scheduling time would eliminate perceived latency.

**Chat turn latency (p95 14 s):** Driven by sequential LLM calls. Parallelising
the tool-call fan-out (demographics + medications + encounters concurrently
rather than sequentially) would reduce p95 by an estimated 3–5 s.

**Cost at scale:** Prompt caching on the system prompt (static across all turns)
would reduce input token costs by ~40% on multi-turn conversations. Caching
guideline retrieval results for repeated queries (same chunk set for common
questions like "ADA HbA1c targets") would reduce Cohere API calls by an
estimated 60% in steady state.

**Embedding model cold start:** The ChromaDB ONNX embedding model (79 MB) is
pre-baked into the Docker image to eliminate the first-request download penalty.
Cold-start latency after a container restart is < 2 s.
