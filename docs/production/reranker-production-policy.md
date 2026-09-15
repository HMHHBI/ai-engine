# Production Reranker Release Policy & Performance Gates (P3-07)

## 1. Executive Summary
Following the implementation of `CrossEncoderRerankerProvider` using `cross-encoder/ms-marco-MiniLM-L-6-v2` in P3-06, this document establishes formal quality, latency, operational, and rollback release gates. 

**Status:** `APPROVED FOR CONTROLLED PRODUCTION ACTIVATION`  
**Production Default:** `ENABLE_RERANKING=False`

---

## 2. Quantitative Gate Verification

### Quality Release Gates (120 Golden Retrieval Queries)
| Gate | Metric | Policy Threshold | Observed Benchmark | Status |
| :--- | :--- | :--- | :--- | :--- |
| **Q1** | **Hit@1** | $\ge 85.00\%$ | **88.33%** | **PASS** |
| **Q2** | **MRR@5** | $\ge 0.9000$ | **0.9267** | **PASS** |
| **Q3** | **Recall@5** | $\ge 98.00\%$ | **98.33%** | **PASS** |
| **Q4** | **Hit@1 Lift** | $\ge +2.00\text{ pp}$ over Hybrid | **+5.00 pp** ($83.33\% \rightarrow 88.33\%$) | **PASS** |

*Tradeoff Assessment:* The cross-encoder trades a marginal $0.84\text{ pp}$ drop in top-5 recall for a substantial $+5.00\text{ pp}$ lift in rank 1 hit rate. For generative RAG context grounding, top-1 relevance directly optimizes LLM synthesis fidelity.

### Latency Release Gates (Warm CPU Inference, 20 Candidates)
| Gate | Metric | Policy Threshold | Observed Benchmark | Status |
| :--- | :--- | :--- | :--- | :--- |
| **L1** | **Rerank p50** | $\le 150.0\text{ ms}$ | **131.41 ms** | **PASS** |
| **L2** | **Rerank p95** | $\le 250.0\text{ ms}$ | **218.95 ms** | **PASS** |
| **L3** | **Total Pipeline p50** | $\le 175.0\text{ ms}$ | **148.48 ms** | **PASS** |
| **L4** | **Total Pipeline p95** | $\le 300.0\text{ ms}$ | **237.88 ms** | **PASS** |

---

## 3. Operational Policy & Safety Architecture

1. **Production Safety Default (`ENABLE_RERANKING=False`):**
   - The default configuration leaves reranking disabled to prevent unexpected CPU load spikes in resource-constrained environments.
2. **Cold Start & Warmup Protocol:**
   - Model weights require approximately $\approx 13.87\text{ s}$ during initial instantiation.
   - Production readiness checks must execute a synthetic warm-up pass upon container boot before exposing reranker-enabled worker nodes to live user traffic.
3. **Deterministic Failure Fallback:**
   - If model inference raises an exception or the model fails to load, `chat.py` catches the error, logs an operational warning, and falls back to slicing the top $K_{final}=6$ hybrid retrieval chunks. No user request fails with a 500 error due to reranker downtime.
4. **Worker Isolation & Concurrency:**
   - A single `CrossEncoder` model is instantiated per Python worker process and guarded by `threading.Lock()` during batch inference.
   - Non-blocking execution is guaranteed via `asyncio.to_thread()`.
5. **Tenant & Auth Isolation:**
   - Reranking operates strictly on pre-authorized candidate pools returned by `search_hybrid_chunks()`. It performs no database reads and cannot bypass tenant scoping.

---

## 4. Rollback Procedure
If latency spikes or memory constraints occur in production after activation:
1. Set environment variable `ENABLE_RERANKING=false`.
2. Restart backend workers. The system immediately reverts to pure hybrid retrieval ($K=6$).
