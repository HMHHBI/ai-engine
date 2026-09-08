# AI Engine

Production-grade full-stack AI application with authenticated chat, multi-provider LLM streaming, PDF/RAG retrieval, vector search, persisted citations, multimodal input, document workspace management, chat personas, custom instructions, and operational observability.

**Branch:** `main`

**Backend:** FastAPI / Python 3.11

**Frontend:** Next.js 16 / React 19 / TypeScript

**Database:** PostgreSQL + pgvector

**Cache / Rate Limiting:** Redis

**Deployment:** Vercel + Render

**CI:** GitHub Actions

**Status:** Production — GO

---

## Overview

AI Engine is a full-stack AI application built as a separated frontend/backend system.

The application provides:

* Google OAuth authentication
* JWT-based authenticated sessions
* Persistent multi-user chat history
* Multiple LLM providers and models
* Structured Server-Sent Events (SSE) streaming
* PDF upload and ingestion
* Gemini/Ollama embeddings
* PostgreSQL + pgvector similarity search
* Retrieval-Augmented Generation (RAG)
* Persisted RAG source/citation metadata
* Document Workspace with per-chat document isolation
* Explicit document selection with newest-ready fallback
* Chat personas and custom instructions
* Image/multimodal input
* Request correlation IDs
* Structured JSON operational logging
* Canonical error taxonomy
* Rate limiting
* Database and Redis health/readiness probes
* Failure recovery without application restart
* Production-oriented migration and deployment safeguards

---

# Architecture

```text
                           ┌─────────────────────────────┐
                           │          User / Browser      │
                           └──────────────┬──────────────┘
                                          │
                                          │ HTTPS
                                          ▼
                    ┌──────────────────────────────────────┐
                    │          Vercel Production            │
                    │                                      │
                    │   Next.js 16 + React 19 + TypeScript │
                    │                                      │
                    │   ┌────────────┐  ┌───────────────┐ │
                    │   │ Auth / JWT │  │ Chat UI       │ │
                    │   └────────────┘  └───────────────┘ │
                    │                                      │
                    │   ┌────────────┐  ┌───────────────┐ │
                    │   │ Zustand    │  │ SSE Client    │ │
                    │   │ Stores     │  │ Stream Guard  │ │
                    │   └────────────┘  └───────────────┘ │
                    └──────────────────┬───────────────────┘
                                       │
                         REST + SSE /chat/stream
                                       │
                                       ▼
                    ┌──────────────────────────────────────┐
                    │          Render Web Service           │
                    │                                      │
                    │               FastAPI                │
                    │                                      │
                    │  Correlation ID Middleware            │
                    │  CORS / Rate Limiting                 │
                    │  Error Taxonomy / Exception Boundary │
                    │  Authentication / Authorization      │
                    │                                      │
                    │  ┌────────────────────────────────┐  │
                    │  │       Chat API / Service         │  │
                    │  │                                │  │
                    │  │  Provider Resolution           │  │
                    │  │  Document Resolution           │  │
                    │  │  RAG Retrieval                 │  │
                    │  │  SSE Generation                │  │
                    │  │  Persistence                   │  │
                    │  └───────────────┬────────────────┘  │
                    │                  │                   │
                    │       ┌──────────┴──────────┐        │
                    │       │                     │        │
                    │       ▼                     ▼        │
                    │  Embedding Service      LLM Factory  │
                    └───────┼─────────────────────┼────────┘
                            │                     │
             ┌──────────────┼──────────┐     ┌────┼──────────────┐
             │              │          │     │    │              │
             ▼              ▼          ▼     ▼    ▼              ▼
       ┌──────────┐   ┌─────────┐ ┌───────┐ ┌───────┐ ┌────────┐
       │ Supabase │   │ Upstash │ │Cloud- │ │Gemini │ │ Ollama │
       │PostgreSQL│  │  Redis  │ │inary  │ │       │ │        │
       │ + pgvector│ │         │ │       │ │       │ │        │
       └──────────┘   └─────────┘ └───────┘ └───────┘ └────────┘
                                                │
                                                ▼
                                           ┌────────┐
                                           │ OpenAI │
                                           └────────┘
```

---

# Request / RAG Flow

```text
User prompt
    │
    ▼
Next.js Chat UI
    │
    │ POST /chat/stream
    │ Authorization: Bearer <JWT>
    ▼
FastAPI
    │
    ├── Authenticate user
    ├── Validate request
    ├── Resolve provider/model
    │
    ├── Document explicitly selected?
    │       │
    │       ├── yes → validate ownership + ready state
    │       │
    │       └── no
    │             │
    │             ▼
    │       Resolve newest ready document
    │
    ├── Document available?
    │       │
    │       └── yes
    │             │
    │             ▼
    │       Generate embedding
    │             │
    │             ▼
    │       pgvector similarity search
    │             │
    │             ▼
    │       Ranked source chunks
    │
    ▼
LLM Provider
    │
    ├── stream_started
    ├── sources
    ├── chunk
    ├── chunk
    ├── ...
    └── stream_completed
            │
            ▼
Next.js SSE parser
    │
    ▼
Zustand chat state
    │
    ├── assistant response
    └── source metadata
            │
            ▼
Citation UI
```

---

# Monorepo Layout

```text
ai-engine/

│
├── backend/
│   ├── app/
│   │   ├── api/
│   │   │   ├── auth.py
│   │   │   ├── chat.py
│   │   │   ├── documents.py
│   │   │   ├── health.py
│   │   │   ├── user.py
│   │   │   └── v1_router.py
│   │   │
│   │   ├── core/
│   │   │   ├── config.py
│   │   │   ├── error_codes.py
│   │   │   ├── exceptions.py
│   │   │   ├── logging.py
│   │   │   ├── middleware.py
│   │   │   └── rate_limiter.py
│   │   │
│   │   ├── db/
│   │   │   ├── models.py
│   │   │   └── session.py
│   │   │
│   │   ├── repositories/
│   │   │   ├── chat_repo.py
│   │   │   ├── document_repo.py
│   │   │   └── vector_repo.py
│   │   │
│   │   ├── schemas/
│   │   │   ├── chat_schema.py
│   │   │   └── document_schema.py
│   │   │
│   │   ├── services/
│   │   │   ├── chat_service.py
│   │   │   ├── document_ingestion_service.py
│   │   │   ├── embedding_service.py
│   │   │   └── providers/
│   │   │
│   │   └── utils/
│   │       ├── file_validation.py
│   │       └── pdf_extractor.py
│   │
│   ├── alembic/
│   │   └── versions/
│   │
│   ├── tests/
│   ├── alembic.ini
│   ├── Dockerfile
│   ├── main.py
│   └── requirements.txt
│
├── frontend/
│   ├── src/
│   │   ├── app/
│   │   ├── features/
│   │   │   ├── auth/
│   │   │   ├── chat/
│   │   │   └── documents/
│   │   ├── lib/
│   │   │   ├── api/
│   │   │   └── errors/
│   │   ├── stores/
│   │   └── types/
│   │
│   ├── public/
│   ├── package.json
│   ├── next.config.ts
│   ├── tsconfig.json
│   └── .env.example
│
└── README.md
```

The frontend is an **in-place Next.js replacement** for the legacy Vue frontend.

There is no separate `frontend-next/` application.

---

# Core Capabilities

## Authentication

* Google OAuth 2.0
* JWT bearer authentication
* Authenticated API requests
* Protected chat operations
* User-scoped resources
* Logout and re-authentication

## AI Providers

The backend currently defines these canonical provider/model combinations:

| Provider | Model              |
| -------- | ------------------ |
| Ollama   | `llama3.2`         |
| Ollama   | `deepseek-r1`      |
| Gemini   | `gemini-2.5-flash` |
| OpenAI   | `gpt-4o-mini`      |

Provider/model configuration is resolved centrally and validated before streaming.

## RAG

PDF processing pipeline:

```text
PDF upload
    ↓
File validation
    ↓
PDF extraction
    ↓
Text chunking
    ↓
Embedding generation
    ↓
PostgreSQL + pgvector
    ↓
Document-scoped similarity search
    ↓
Ranked chunks
    ↓
LLM context
    ↓
Answer + persisted source metadata
```

The production system uses PostgreSQL with pgvector for vector retrieval.

---

# Document Workspace

Documents are first-class resources scoped through the ownership chain:

```text
User
 └── Chat
      └── Document
           └── DocumentChunk
```

Each document belongs to both a user and a chat.

Document lifecycle states are:

```text
processing
ready
failed
```

Document operations enforce user → chat → document ownership.

For RAG requests:

* an explicitly selected document is used when supplied
* the selected document must belong to the authenticated user and target chat
* the selected document must be `ready`
* invalid explicit selections return an error and do not silently fall back
* when no document is selected, retrieval automatically uses the newest ready document for the chat

Vector retrieval is strictly document-scoped.

The frontend provides document workspace controls for:

* listing documents
* selecting a document for chat retrieval
* uploading PDFs
* observing processing status
* editing supported metadata
* deleting documents
* clearing a deleted document's active selection

---

# Chat Personas & Custom Instructions

Each chat can optionally define:

* a persona
* custom instructions

These settings are persisted with the chat and incorporated into the runtime system prompt.

The effective prompt layers are:

```text
Base system behavior
        ↓
Persona guidelines
        ↓
Custom instructions
        ↓
RAG context
        ↓
User request
```

Persona and instruction updates are ownership-scoped to the authenticated chat owner.

---

# Streaming

AI responses use structured Server-Sent Events rather than a single blocking response.

The stream supports:

```text
stream_started
sources
chunk
stream_completed
stream_error
stream_cancelled
```

The frontend protects against:

* stale streams
* chat switching races
* retry races
* cancellation races
* deletion during streaming
* late events from previous requests

Exactly one terminal stream state is expected.

---

# Citations

RAG source metadata is emitted separately from generated text through the SSE `sources` event.

Sources are persisted with the completed assistant message in PostgreSQL and restored when chat history is hydrated.

Persisted citation metadata includes:

* source document chunk ID
* page number
* chunk index
* retrieval distance

Internal retrieval details are sanitized before persistence or client exposure.

The frontend renders persisted citations through the citation UI.

---

# Multimodal Input

The frontend supports image attachments with a maximum of four images per request.

Object URLs are cleaned up when no longer required.

---

# Observability

Production logging uses structured JSON records.

Core fields include:

```text
timestamp
level
logger
event
correlation_id
```

Sensitive payloads are excluded or redacted, including:

```text
prompt
tokens
extracted_text
authorization
cookie
credentials
API keys
```

AI/RAG telemetry records operational metadata such as:

* provider
* model
* retrieval duration
* retrieved chunk count
* time to first token
* stream duration
* emitted chunk count
* terminal lifecycle state

Generated prompts, completions, PDF contents, embeddings, JWTs, and credentials are not logged.

---

# Health Endpoints

## Liveness

```http
GET /health/live
```

Expected:

```json
{
  "status": "ok"
}
```

This endpoint does not require database or Redis availability.

## Readiness

```http
GET /health/ready
```

Expected:

```json
{
  "status": "ready",
  "checks": {
    "database": "ok",
    "redis": "ok"
  }
}
```

Readiness independently verifies:

* PostgreSQL using `SELECT 1`
* Redis using `PING`

A dependency failure produces HTTP `503`.

---

# Docker

The backend is containerized using Python 3.11.

From `backend/`:

```bash
docker build -t ai-engine-backend .
```

Run:

```bash
docker run --env-file .env -p 8000:8000 ai-engine-backend
```

The backend image is based on `python:3.11-slim`.

---

# Local Development

## Backend

```bash
cd backend
python -m venv .venv
```

Windows:

```powershell
.venv\Scripts\Activate.ps1
```

Install:

```bash
pip install -r requirements.txt
```

Run migrations:

```bash
alembic upgrade head
```

Start:

```bash
uvicorn main:app --reload
```

Backend:

```text
http://localhost:8000
```

## Frontend

```bash
cd frontend
npm install
npm run dev
```

Frontend:

```text
http://localhost:3000
```

---

# Production Deployment

## Frontend — Vercel

The `frontend/` directory is the Vercel Root Directory.

Production deployment uses:

```text
Vercel
└── frontend/
    └── Next.js
```

Required public environment variables:

```text
NEXT_PUBLIC_API_URL
NEXT_PUBLIC_GOOGLE_CLIENT_ID
```

## Backend — Render

Production backend:

```text
Render Web Service
└── ai-engine
    └── Working Directory: backend/
```

The production startup command enforces migration-before-server startup:

```bash
alembic upgrade head && uvicorn main:app --host 0.0.0.0 --port $PORT
```

This provides the deployment invariant:

```text
Migration succeeds
      ↓
Uvicorn starts
      ↓
Port binds
      ↓
Traffic becomes available
```

If migration fails, the server does not start.

Render health check:

```text
/health/ready
```

---

# Database & State Infrastructure

## Supabase

Production PostgreSQL database with:

* PostgreSQL
* pgvector
* relational user/chat/message storage
* document and document chunk storage
* vector retrieval
* automated database infrastructure/backups provided by the platform

## Upstash Redis

Used for:

* rate limiting
* readiness verification

## Cloudinary

Used for backend-managed media storage/integration.

Credentials remain server-side.

---

# Database Migrations

The project currently has one Alembic head:

```text
c7efc0cfd435
```

Migration chain:

```text
744e13609578
       ↓
19b113b14a35
       ↓
444652176ea6
       ↓
d3ba22db292b
       ↓
7a99b1a5acae
       ↓
21f288e57a41
       ↓
e1256d638e34
       ↓
c7efc0cfd435
```

The migration history is linear.

Key milestones include:

* PostgreSQL + pgvector initialization
* document chunk metadata
* chat embedding provider configuration
* reset-token hardening
* persisted message sources
* chat personas and custom instructions
* Document Workspace creation
* document/chunk linkage

Run locally:

```bash
alembic upgrade head
```

Verify:

```bash
alembic current
alembic heads
```

There should be exactly one head:

```text
c7efc0cfd435
```

---

# Continuous Integration

GitHub Actions runs on pull requests targeting `main`.

The CI pipeline verifies:

## Backend

* Python 3.11
* PostgreSQL 16 with pgvector
* Redis 7
* Alembic migrations
* backend test suite

## Frontend

* Node.js 20
* `npm ci`
* Vitest tests
* ESLint
* production build

The CI environment uses PostgreSQL/pgvector and Redis service containers to exercise the backend against production-relevant infrastructure.

CI does not deploy automatically.

---

# Production Verification

Final backend verification:

```text
185 / 185 tests passing
```

Production smoke testing has verified:

* Google authentication
* JWT session management
* chat creation
* chat history
* rename
* deletion
* PDF ingestion
* document workspace
* document selection
* document ownership isolation
* vector retrieval
* provider failure handling
* safe error responses
* correlation IDs
* production health/readiness
* persisted citation hydration
* chat persona/custom instruction behavior

Frontend production verification includes:

* Vitest suite
* ESLint
* Next.js production build
* responsive/mobile behavior
* accessibility checks
* streaming race protection
* document workspace lifecycle
* citation rendering
* document selection integration

---

# Security Model

The application enforces:

* JWT authentication
* user ownership checks
* IDOR protection
* authenticated chat access
* user/chat/document ownership validation
* document-scoped vector retrieval
* explicit CORS origins
* rate limiting
* upload size/page/chunk limits
* PDF signature validation
* safe exception responses
* structured sensitive-data redaction
* environment-based secrets
* no wildcard production CORS

Internal database, provider, and infrastructure exceptions are not exposed directly to clients.

Explicit document selection does not silently fall back when the supplied document is invalid or unauthorized.

---

# Release Status

```text
Phase 5.1  Production Configuration        ✅
Phase 5.2  Security & Secret Hardening     ✅
Phase 5.3  Reliability Verification        ✅
Phase 5.4  DB / Migration / Recovery       ✅
Phase 5.5  Production Deployment/Smoke     ✅
Phase 5.6  Final Release Gate              ✅
```

**Release decision: GO**

The current `main` branch represents the production application baseline.

---

# Known Operational Contracts

## Citation persistence

Citation metadata is emitted through the live SSE `sources` event and persisted with completed assistant messages.

Persisted citations are restored when chat history is hydrated.

## Document selection

A chat may optionally select a specific ready document for RAG retrieval.

When no document is selected, the backend automatically resolves the newest ready document for the chat.

An explicitly supplied invalid, unauthorized, processing, failed, cross-chat, or cross-user document does not trigger fallback retrieval.

## Local LLM fallback

Ollama remains supported by the application architecture, but the production cloud deployment does not host a local Ollama daemon on the free-tier infrastructure.

---

# Author

**Hassan — HMHHBI**

GitHub: `https://github.com/HMHHBI`

---

# License

MIT License.

See `LICENSE` for the full license text.
