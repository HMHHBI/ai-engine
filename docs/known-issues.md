# Known Issues & V1 Architecture Boundaries

This document records accepted design decisions, non-blocking limitations, and intentional boundaries for the AI Engine V1.0.0 release.

## 1. Authentication & Session Management
- **Token Storage**: The frontend stores JWT access tokens in browser `localStorage`.
  - *Risk Evaluation*: Standard Single-Page Application (SPA) exposure surface; mitigated by strict Content Security Policy (CSP), explicit `ALLOWED_ORIGINS` CORS headers, and absence of user-injected raw HTML rendering.
  - *Future Roadmap (V2)*: Transition to `httpOnly` secure cookies with explicit CSRF token verification.

## 2. Ingestion Worker Deployment Topology
- **In-Process Worker Execution**: `DocumentIngestionWorker` runs within the FastAPI lifespan context via `asyncio.create_task`.
  - *Intended Deployment*: Single-instance or container-level vertical scaling (Render / Docker single replica).
  - *Boundary Limitation*: Running multiple horizontally auto-scaled API containers against the same Redis queue requires moving the worker into an independent dedicated background service to prevent redundant consumer leases.

## 3. Storage Backends
- **Development vs. Production**:
  - `local`: Direct filesystem storage inside `backend/uploads` (default for local setups).
  - `r2`: S3-compatible object storage via Cloudflare R2 (requires `R2_ACCOUNT_ID`, `R2_ACCESS_KEY_ID`, `R2_SECRET_ACCESS_KEY`, and `R2_BUCKET_NAME`).

## 4. Vector Dimensions & HNSW Indexes
- Vector dimensions in PostgreSQL are configured for the active embedding provider model (e.g., 1536 for OpenAI `text-embedding-3-small`, 768 for Gemini/Ollama). Switching providers on an existing database requires rebuilding or re-indexing document embeddings.
