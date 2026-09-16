# P3-08 Security & Abuse-Resistance Reassessment

## 1. Scope
Reassessment of security boundaries, multi-document tenant isolation, prompt-injection context separation, reranker resource bounds, fallback mechanisms, and real rate-limiting enforcement following the integration of Phase 3 retrieval and reranking enhancements.

## 2. Security Surface Reviewed
- `backend/app/api/chat.py` (Authorization scoping, streaming lifecycle, rate-limiting decorators, prompt assembly)
- `backend/app/repositories/chat_repo.py` & `document_repo.py` (Tenant-scoped database queries)
- `backend/app/repositories/vector_repo.py` (Hybrid search document and user scoping)
- `backend/app/services/reranker_service.py` (CrossEncoder model isolation, thread locks, candidate size boundaries)
- `backend/app/core/rate_limiter.py` (SlowAPI rate limiting middleware and storage)

## 3. RAG Authorization & Multi-Document Isolation
- **Cross-user chat & document scoping:** Unauthorized users cannot access or stream chats belonging to other users (HTTP 403/404).
- **Multi-document isolation:** Vector hybrid search explicitly filters by `user_id` and active `document_id`. Where a user owns multiple documents (e.g., Doc A and Doc B), queries scoped to Doc A retrieve only Doc A chunks. Doc B chunks are strictly excluded from retrieval, reranking, and downstream LLM context.
- **Reranker boundary:** `_build_rerank_candidates` operates exclusively on pre-authorized chunks. The reranker performs zero independent database queries.

## 4. Prompt-Injection Boundary Invariant
- **Application-level context encapsulation:** Injected instructions inside retrieved chunks (e.g., `IGNORE ALL PREVIOUS INSTRUCTIONS`) remain strictly enclosed inside `RETRIEVED DOCUMENT CONTEXT:` delimiters.
- **System instruction immutability:** Core system instructions (`RULES:` and grounding constraints) remain un-overridden by injected chunk text or custom instructions.
- **Boundary Qualification:** This design establishes an application-level prompt/context boundary invariant; downstream stochastic model adherence remains governed by model alignment.

## 5. Reranker Resource-Abuse & Fallback Integration
- **Pipeline Input Hard Cap:** When hybrid retrieval yields up to 50 candidates, the `/chat/stream` pipeline enforces `RERANK_INITIAL_K = 20` candidates passed to `RerankerService.rerank`.
- **Output Truncation:** Output candidate lists are strictly capped at `RERANK_FINAL_K = 6`.
- **Deterministic Failure Fallback:** If `RerankerService.rerank` encounters an unhandled exception or model failure during `/chat/stream`, the pipeline catches the exception, logs `rag_reranking_fallback_triggered`, returns HTTP 200, and gracefully falls back to the top `RERANK_FINAL_K` unranked hybrid chunks.
- **Thread Safety & Serialization:** Inference is wrapped in an internal threading lock, preventing concurrent thread corruption.

## 6. Rate-Limit Enforcement
- **Real Limiter Verification:** `/chat/stream` is bounded to 15 requests/minute.
- **Boundary short-circuiting:** A real integration test verifies that exhausting the 15-request quota triggers HTTP 429 on the 16th request, terminating the request before embedding, retrieval, reranker, or LLM stream execution.

## 7. Security Regression Invariants
- **Authentication:** Unauthenticated endpoints correctly reject requests with HTTP 401.
- **Error sanitization:** Unhandled 500 exceptions suppress database credentials, filesystem paths, and internal stack traces from the response body.

## 8. S1–S20 Acceptance Criteria & Evidence Matrix

| Criterion | Description | Evidence / Verification Method | Status |
| :--- | :--- | :--- | :--- |
| **S1** | Cross-user chat access denied | `test_s1_cross_user_chat_access_denied` (HTTP 403/404) | PASS |
| **S2** | Multi-document isolation (Doc A vs Doc B) | `test_s1_multi_document_isolation_boundary` (Doc B excluded from context) | PASS |
| **S3** | Pre-authorized reranker candidate pool | `test_s1_reranker_operates_only_on_authorized_pool` | PASS |
| **S4** | Context enclosure of malicious prompt instructions | `test_s2_malicious_document_instruction_contained_in_context` | PASS |
| **S5** | Custom instructions cannot overwrite system rules | `test_s2_custom_instructions_cannot_bypass_rules` | PASS |
| **S6** | Reranker input budget hard cap (Initial K=20) | `test_s3_pipeline_enforces_initial_k_budget_to_reranker` | PASS |
| **S7** | Reranker output hard cap (Final K=6) | `test_s3_pipeline_enforces_initial_k_budget_to_reranker` & `app/api/chat.py` | PASS |
| **S8** | Safe fallback on reranker model failure | `test_s3_reranker_failure_fallback_through_chat_stream` (HTTP 200 fallback) | PASS |
| **S9** | Provider score failure exception safety | `test_s3_reranker_model_load_failure_safety` | PASS |
| **S10** | Thread serialization and inference locking | `test_s3_concurrent_rerank_thread_safety` | PASS |
| **S11** | Real route rate-limit enforcement (15/min) | `test_s4_real_limiter_rejects_on_limit_and_blocks_pipeline` (HTTP 429) | PASS |
| **S12** | Expensive pipeline short-circuit on rate limit | `test_s4_real_limiter_rejects_on_limit_and_blocks_pipeline` (zero downstream calls) | PASS |
| **S13** | Unauthenticated stream access rejected | `test_s5_unauthenticated_request_rejected` (HTTP 401) | PASS |
| **S14** | 500 internal error credential redaction | `test_s5_internal_error_does_not_leak_internals` | PASS |
| **S15** | Safe production operational default | P3-07 Gate O1 (`ENABLE_RERANKING=False`) | PASS |
| **S16** | Cross-tenant document delete protection | `tests/test_document_repository.py` & ownership checks | PASS |
| **S17** | PDF upload size and MIME verification | `tests/test_upload_security.py` | PASS |
| **S18** | SQL/pgvector injection resistance | SQLAlchemy parameterized queries in `VectorRepository` | PASS |
| **S19** | Zero evaluation leak in version control | Clean `.gitignore` with `.gitkeep` retention | PASS |
| **S20** | Full backend test baseline regression | 350+ passing backend tests (0 failures) | PASS |

## 9. Findings
All 6 evidence gaps identified during review have been resolved with real integration tests against the actual route and pipeline boundaries.

## 10. Residual Risks
- `ENABLE_RERANKING=False` remains the mandatory production default due to CPU inference overhead during burst traffic. Controlled activation requires worker thread capacity planning.

## 11. Final Verdict
**PASS**
