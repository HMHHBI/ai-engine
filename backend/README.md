# AI Engine Backend

Production FastAPI backend for the AI Engine application.

**Runtime:** Python 3.11
**Framework:** FastAPI
**Database:** PostgreSQL + pgvector
**Cache / Rate Limiting:** Redis
**AI Providers:** Gemini, Ollama, OpenAI
**Migrations:** Alembic
**Production:** Render
**Release baseline:** `27882ed`

---

# Architecture

```text
                         FastAPI Application
                                │
                ┌───────────────┴────────────────┐
                │                                │
        Correlation Middleware            Rate Limiting
                │                                │
                └───────────────┬────────────────┘
                                │
                         API Routers
                                │
              ┌─────────────────┼─────────────────┐
              │                 │                 │
             Auth             Chat              User
                                │
                       Chat Application Service
                                │
             ┌──────────────────┼──────────────────┐
             │                  │                  │
       Chat Repository    Vector Repository   Provider Factory
             │                  │                  │
             │                  ▼                  │
             │            pgvector RAG             │
             │                                     │
             │                          ┌──────────┼─────────┐
             │                          │          │         │
             ▼                          ▼          ▼         ▼
        PostgreSQL                   Gemini     Ollama    OpenAI
```

---

# Project Structure

```text
backend/
│
├── app/
│   ├── api/
│   │   ├── auth.py
│   │   ├── chat.py
│   │   ├── health.py
│   │   ├── user.py
│   │   └── v1_router.py
│   │
│   ├── core/
│   │   ├── config.py
│   │   ├── error_codes.py
│   │   ├── exceptions.py
│   │   ├── logging.py
│   │   ├── middleware.py
│   │   └── rate_limiter.py
│   │
│   ├── db/
│   │   ├── models.py
│   │   └── session.py
│   │
│   ├── repositories/
│   │   ├── chat_repo.py
│   │   └── vector_repo.py
│   │
│   ├── schemas/
│   │   └── chat_schema.py
│   │
│   ├── services/
│   │   ├── chat_service.py
│   │   ├── embedding_service.py
│   │   └── providers/
│   │
│   └── utils/
│       ├── file_validation.py
│       └── pdf_extractor.py
│
├── alembic/
│   ├── env.py
│   └── versions/
│
├── tests/
├── alembic.ini
├── Dockerfile
├── main.py
└── requirements.txt
```

---

# API Layers

## `api/`

HTTP boundary.

Responsibilities include:

* authentication
* request validation
* chat operations
* streaming responses
* file uploads
* health checks
* user endpoints

## `services/`

Application/business orchestration.

Examples:

* `ChatApplicationService`
* `EmbeddingService`
* provider implementations

## `repositories/`

Persistence and retrieval boundary.

Examples:

* `ChatRepository`
* `VectorRepository`

Repositories enforce ownership/scoping rules before accessing user-specific resources.

## `core/`

Cross-cutting infrastructure:

* configuration
* error taxonomy
* exception handling
* structured logging
* request correlation
* rate limiting

---

# AI Provider Configuration

Canonical providers:

```text
gemini
ollama
openai
```

Canonical models:

```text
gemini-2.5-flash
llama3.2
deepseek-r1
gpt-4o-mini
```

Provider/model selection is validated against the canonical registry.

Default configuration currently defined by the application includes:

```text
DEFAULT_AI_PROVIDER=ollama
DEFAULT_AI_MODEL=llama3.2
DEFAULT_EMBEDDING_PROVIDER=ollama
```

Production can select cloud providers through environment configuration.

---

# Streaming API

Primary AI endpoint:

```http
POST /chat/stream
```

Request model:

```json
{
  "chat_id": 1,
  "prompt": "Explain quantum computing",
  "task": "general",
  "model": "gemini-2.5-flash",
  "provider": "gemini",
  "file_context": null,
  "image_base64": [],
  "image_mime": []
}
```

The model and provider fields are optional and are resolved against chat/application configuration when necessary.

---

# SSE Protocol

The backend emits structured SSE events.

## Stream started

```text
event: stream_started
data: {"provider":"gemini","model":"gemini-2.5-flash"}
```

## Sources

When RAG retrieval returns chunks:

```text
event: sources
data: {"sources":[...]}
```

Source metadata includes:

```text
id
page_number
chunk_index
distance
```

Chunk text itself is not exposed through the source metadata event.

## Generated chunk

```text
event: chunk
data: {"text":"Quantum "}
```

## Completion

```text
event: stream_completed
data: {"message_id":123}
```

## Provider/application failure

```text
event: stream_error
data: {
  "code": "provider_unavailable",
  "message": "..."
}
```

## Cancellation

```text
event: stream_cancelled
data: {
  "message": "..."
}
```

Exactly one terminal lifecycle state should be emitted for a stream.

---

# RAG Pipeline

```text
PDF
 │
 ▼
Upload validation
 │
 ├── size limit
 ├── extension validation
 ├── content-type validation
 ├── PDF signature validation
 └── page/text/chunk limits
 │
 ▼
PDF text extraction
 │
 ▼
Chunk generation
 │
 ▼
Embedding provider
 │
 ▼
PostgreSQL + pgvector
 │
 ▼
Similarity search
 │
 ▼
Ranked chunks
 │
 ▼
LLM prompt/context
```

Production retrieval uses user and chat scoping to prevent cross-user vector access.

---

# Configuration

Configuration is provided through environment variables using Pydantic Settings.

## Required

```text
DATABASE_URL
FRONTEND_URL
SECRET_KEY
CLOUDINARY_NAME
CLOUDINARY_API_KEY
CLOUDINARY_API_SECRET
```

Production CORS also requires:

```text
ALLOWED_ORIGINS
```

`ALLOWED_ORIGINS` must contain explicit comma-separated origins.

Wildcard CORS is rejected.

---

# Database Configuration

```text
DATABASE_URL
DB_POOL_SIZE=10
DB_MAX_OVERFLOW=20
DB_POOL_TIMEOUT=30
DB_POOL_RECYCLE=1800
DB_POOL_PRE_PING=true
```

SQLAlchemy connection pooling uses pre-ping and bounded pool settings for production resilience.

---

# Authentication / Security Configuration

```text
SECRET_KEY
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=1440
GOOGLE_CLIENT_ID
```

JWT validation rejects:

* missing tokens
* malformed/tampered tokens
* expired tokens
* invalid subjects
* tokens signed with the wrong secret

---

# Upload Security Limits

Defaults:

```text
MAX_UPLOAD_SIZE_BYTES=10485760
MAX_PDF_PAGES=100
MAX_EXTRACTED_TEXT_CHARS=2000000
MAX_DOCUMENT_CHUNKS=5000
MAX_CHUNK_EMBEDDINGS=5000
```

These values are configurable through environment variables.

---

# AI Timeouts

```text
AI_CONNECT_TIMEOUT=10
AI_READ_TIMEOUT=60
AI_WRITE_TIMEOUT=10
AI_POOL_TIMEOUT=5

AI_REQUEST_TIMEOUT=120
AI_STREAM_MAX_SECONDS=120
```

Gemini worker configuration:

```text
GEMINI_MAX_WORKERS=4
GEMINI_WORKER_JOIN_TIMEOUT=0.5
GEMINI_QUEUE_SIZE=32
GEMINI_QUEUE_POLL_SECONDS=0.25
```

---

# AI API Keys

Optional provider credentials:

```text
GEMINI_API_KEY
OPENAI_API_KEY
ANTHROPIC_API_KEY
```

Provider credentials are server-side environment variables and must never be committed to Git.

---

# Ollama

```text
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_LLM_MODEL=llama3.2
OLLAMA_EMBED_MODEL=nomic-embed-text
```

Ollama is supported by the backend architecture.

The production free-tier deployment does not host an Ollama daemon.

---

# Redis

```text
REDIS_HOST=localhost
REDIS_PORT=6379
REDIS_URL=redis://localhost:6379
```

Redis is used by the rate limiter and readiness probe.

Production uses Upstash Redis.

---

# Cloudinary

```text
CLOUDINARY_NAME
CLOUDINARY_API_KEY
CLOUDINARY_API_SECRET
```

These values remain backend-only.

---

# Email

Optional mail configuration:

```text
MAIL_USERNAME
MAIL_PASSWORD
MAIL_FROM
```

---

# Structured Logging

The backend configures structured JSON logging during application startup.

Core record fields:

```text
timestamp
level
logger
event
correlation_id
```

Operational events include examples such as:

```text
application_startup
database_ready
chat_request_started
rag_retrieval_started
rag_retrieval_completed
ai_provider_selected
ai_stream_started
ai_first_token
ai_stream_completed
chat_request_completed
ai_stream_failed
ai_stream_cancelled
chat_request_failed
health_dependency_failed
```

---

# Sensitive Logging Contract

The logging layer must not expose:

```text
prompts
tokens
PDF extracted text
credentials
Authorization headers
cookies
API keys
JWTs
raw request bodies
raw response bodies
embeddings
```

Operational telemetry records metadata rather than sensitive payloads.

For AI generation:

```text
provider
model
chunk_count
duration_ms
time_to_first_token_ms
error_code
```

are acceptable operational metadata.

---

# Correlation IDs

Every request receives a request-scoped correlation ID.

Accepted request headers:

```text
X-Correlation-ID
X-Request-ID
```

Precedence:

```text
X-Correlation-ID
      ↓
X-Request-ID
      ↓
generated UUID
```

The canonical internal field is:

```text
correlation_id
```

The value is propagated through request context and returned as:

```http
X-Correlation-ID: <uuid>
```

The request context is cleaned after request completion.

---

# Error Taxonomy

The backend exposes canonical application error codes through `ErrorCode`.

`AppError` provides:

* canonical error code
* safe client message
* HTTP status
* internal diagnostic context

Clients receive safe messages rather than raw infrastructure exceptions.

Example:

```json
{
  "code": "provider_unavailable",
  "message": "The AI provider is temporarily unavailable. Please try again."
}
```

Internal SQLAlchemy, Redis, provider, and traceback details are not returned to clients.

---

# Health Probes

## Liveness

```http
GET /health/live
```

Response:

```json
{
  "status": "ok"
}
```

HTTP:

```text
200
```

Liveness does not require database or Redis connectivity.

## Readiness

```http
GET /health/ready
```

Healthy response:

```json
{
  "status": "ready",
  "checks": {
    "database": "ok",
    "redis": "ok"
  }
}
```

HTTP:

```text
200
```

Database or Redis failure:

```text
503
```

The checks are bounded and independent.

---

# Alembic Migration Runbook

Current migration head:

```text
7a99b1a5acae
```

Migration chain:

```text
744e13609578
19b113b14a35
444652176ea6
d3ba22db292b
7a99b1a5acae
```

## Step 1 — Inspect current revision

```bash
alembic current
```

Expected production head:

```text
7a99b1a5acae
```

## Step 2 — Inspect migration graph

```bash
alembic heads
```

Expected:

```text
7a99b1a5acae
```

There should be exactly one head.

## Step 3 — Upgrade

```bash
alembic upgrade head
```

This applies all pending migrations transactionally where supported by PostgreSQL.

## Step 4 — Verify revision

```bash
alembic current
```

Confirm:

```text
7a99b1a5acae
```

## Step 5 — Verify application readiness

```bash
curl http://localhost:8000/health/ready
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

---

# Fresh Database Initialization

The migration chain initializes the pgvector extension through the migration that introduces vector support.

The expected migration sequence is:

```text
initial schema
      ↓
document chunks + pgvector
      ↓
chunk metadata
      ↓
chat embedding provider
      ↓
reset token hash + expiry
```

Do not manually mutate production schema outside the migration system.

---

# Production Deployment

Production service:

```text
Render Web Service
Name: ai-engine
Working directory: backend/
```

Startup command:

```bash
alembic upgrade head && uvicorn main:app --host 0.0.0.0 --port $PORT
```

This is the production migration invariant:

```text
alembic upgrade head
       │
       ├── failure → process exits
       │
       └── success
             ↓
       uvicorn starts
             ↓
       $PORT binds
```

Render health check:

```text
/health/ready
```

---

# Docker

Build:

```bash
docker build -t ai-engine-backend .
```

Run:

```bash
docker run --env-file .env -p 8000:8000 ai-engine-backend
```

The production Docker image uses Python 3.11 slim.

For local development, migrations should be run explicitly before starting the application.

---

# Testing

The backend release gate is:

```text
145 / 145 tests passing
```

Run the test suite locally:

```bash
pytest
```

Recommended production-equivalent execution is inside the project Docker environment.

Example:

```bash
docker compose run --rm backend pytest
```

or execute the equivalent project-specific Docker test command used by the development environment.

Expected result:

```text
145 passed
```

---

# Reliability Verification

The backend test suite covers:

* authentication security
* IDOR protection
* vector ownership
* persistence consistency
* upload hardening
* ingestion integrity
* vector concurrency
* streaming reliability
* provider timeout/cancellation
* Gemini worker lifecycle
* rate limiting
* health checks
* canonical error taxonomy
* correlation propagation
* database recovery
* Redis recovery
* rollback after database failure

Failure resilience specifically verifies that transient database and Redis failures can recover without requiring an application/container restart.

---

# Production Baseline

```text
Release:       27882ed
Branch:        main
Alembic head:  7a99b1a5acae
Tests:         145 / 145
Status:        GO
```

The backend is approved for the current production release.
