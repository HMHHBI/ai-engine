# V1 Release Verification Record

- **Release Milestone**: v1.0.0
- **Verified Commit SHA**: f481b32e0a5935762fc8426875790a55cd33d162
- **Date**: October 21, 2026
- **Target Branch**: main

## 1. Automated Test Suite Execution

### Backend (Pytest)
- **Status**: PASSED
- **Total Tests**: 627 passed
- **Duration**: ~3m 00s
- **Coverage Highlights**:
  - Research Synthesis Strict Citation Validation (whitespace padding, multi-ID, C0, C999 rejection)
  - Workspace Role-Based Access Control (RBAC matrix across owner, admin, researcher, viewer)
  - IDOR & Dual Ownership Protection (chat, document, and vector scope)
  - Stream Concurrency, Heartbeat, and Client Disconnect Handling
  - Document Ingestion Worker, Dead Letter Queue (DLQ), and Retries

### Frontend (Vitest & ESLint)
- **Status**: PASSED
- **Test Files**: 52 passed (52)
- **Total Unit/Integration Tests**: 357 passed (357)
- **Linting**: ESLint clean (0 errors)
- **Coverage Highlights**:
  - Workspace document manager & document attachment journeys
  - Citation source collapsible drawers & Markdown table rendering
  - Chat streaming lifecycle, cancellation, and error boundary handling
  - PDF viewer page navigation & synchronization

## 2. Infrastructure & Reproducibility
- **Python**: 3.11.17 (FastAPI, SQLAlchemy, Alembic, psycopg2)
- **Node.js**: 20.x (Next.js 15/16 App Router, React 19, TypeScript)
- **Database**: PostgreSQL 16 with `pgvector` extension
- **Cache/Queue**: Redis 7
- **Database Seed Script**: `scripts/seed_m3_test_data.py` verified idempotent with clean foreign key and membership resolution.
