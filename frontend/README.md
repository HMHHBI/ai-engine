# AI Engine Frontend

Production Next.js client for the AI Engine application.

**Framework:** Next.js 16
**React:** 19
**Language:** TypeScript
**Styling:** Tailwind CSS
**State:** Zustand
**Icons:** lucide-react
**Testing:** Vitest + React Testing Library
**Deployment:** Vercel
**Production baseline:** `27882ed`

---

# Overview

The frontend is the production client for the FastAPI AI Engine backend.

It provides:

* Google OAuth sign-in
* JWT session handling
* protected application routing
* chat history
* chat creation
* chat rename/delete
* AI streaming
* model/provider selection
* PDF upload lifecycle
* RAG source presentation
* collapsible citations
* image attachments
* responsive/mobile UI
* accessible keyboard interactions
* loading/error/empty states
* streaming cancellation and retry protection

The current application is an **in-place replacement of the legacy Vue frontend**.

There is no separate `frontend-next/` directory.

---

# Architecture

```text
frontend/
│
├── src/
│   │
│   ├── app/
│   │   ├── page
│   │   ├── login/
│   │   ├── signup/
│   │   ├── forgot-password/
│   │   └── dashboard/
│   │
│   ├── features/
│   │   ├── auth/
│   │   │   ├── actions/
│   │   │   └── components/
│   │   │
│   │   └── chat/
│   │       ├── actions/
│   │       ├── components/
│   │       ├── integration/
│   │       ├── regression/
│   │       ├── store/
│   │       └── stream/
│   │
│   ├── lib/
│   │   ├── api/
│   │   └── errors/
│   │
│   ├── stores/
│   │
│   └── types/
│
├── public/
├── package.json
├── next.config.ts
├── tsconfig.json
└── .env.example
```

---

# Feature Architecture

The frontend follows feature-oriented boundaries.

```text
                    Next.js App Router
                           │
             ┌─────────────┴─────────────┐
             │                           │
          Auth Feature              Chat Feature
             │                           │
      ┌──────┴──────┐          ┌─────────┴──────────┐
      │             │          │                    │
   Actions      Components   Actions             Components
                                  │
                                  ▼
                         Stream / Request Control
                                  │
                                  ▼
                              API Layer
                                  │
                                  ▼
                              FastAPI
```

---

# State Management

Zustand stores separate application concerns.

Chat state includes:

```text
activeChatId
messagesByChat
loadingChatIds
streamingStatusByChat
pdfStateByChat
```

Chat session state includes:

```text
sessions
isLoading
error
mutatingChatIds
```

This separation prevents UI state, chat message state, and session-list state from becoming one monolithic store.

---

# Authentication Flow

```text
User
 │
 ▼
Google Sign-In
 │
 ▼
Google credential
 │
 ▼
Backend authentication
 │
 ▼
JWT
 │
 ▼
Browser session state
 │
 ▼
Protected dashboard
 │
 ▼
Bearer token on API requests
```

The streaming service reads the JWT from browser storage when running in the browser and attaches:

```http
Authorization: Bearer <token>
```

to the stream request.

---

# Environment Variables

The frontend requires only public environment configuration.

`.env.example`:

```bash
NEXT_PUBLIC_API_URL=YOUR_BACKEND_API_URL
NEXT_PUBLIC_GOOGLE_CLIENT_ID=YOUR_GOOGLE_CLIENT_ID
```

## `NEXT_PUBLIC_API_URL`

Production API origin.

Example:

```text
https://ai-engine-d9lm.onrender.com
```

## `NEXT_PUBLIC_GOOGLE_CLIENT_ID`

Google OAuth client ID used by the browser-side Google Sign-In integration.

These values are intentionally `NEXT_PUBLIC_*` because they are client-visible configuration.

Do not place backend secrets in the frontend environment.

---

# SSE Streaming

The primary streaming endpoint is:

```http
POST /chat/stream
```

The frontend uses a dedicated `ChatStreamService`.

```text
frontend/src/features/chat/stream/chat-stream-service.ts
```

The service:

* creates an `AbortController`
* sends the authenticated request
* parses SSE framing
* supports fragmented network chunks
* normalizes CRLF/LF line endings
* ignores SSE comments/heartbeats
* validates source metadata
* maps server events into typed frontend events
* detects cancellation
* rejects HTTP failures
* handles malformed SSE JSON
* prevents stale streams from mutating current state

---

# Stream Event Mapping

Backend events are mapped into frontend events.

| Backend SSE event  | Frontend event    |
| ------------------ | ----------------- |
| `stream_started`   | `streamStarted`   |
| `sources`          | `sourcesReceived` |
| `chunk`            | `chunkReceived`   |
| `stream_completed` | `streamCompleted` |
| `stream_cancelled` | `streamCancelled` |
| `stream_error`     | `streamFailed`    |

---

# `stream_started`

Example:

```text
event: stream_started
data: {"provider":"gemini","model":"gemini-2.5-flash"}
```

Frontend receives:

```ts
{
  type: "streamStarted",
  provider: "gemini",
  model: "gemini-2.5-flash"
}
```

---

# `sources`

Example:

```text
event: sources
data: {
  "sources": [
    {
      "id": 1,
      "page_number": 4,
      "chunk_index": 2,
      "distance": 0.214
    }
  ]
}
```

Frontend receives:

```ts
{
  type: "sourcesReceived",
  sources: [...]
}
```

Only structurally valid source metadata is accepted.

---

# `chunk`

Example:

```text
event: chunk
data: {"text":"Quantum "}
```

Frontend receives:

```ts
{
  type: "chunkReceived",
  chunk: "Quantum "
}
```

Chunks are appended incrementally to the active assistant message.

---

# `stream_completed`

Example:

```text
event: stream_completed
data: {"message_id":123}
```

Frontend receives:

```ts
{
  type: "streamCompleted",
  messageId: 123
}
```

The assistant message transitions out of streaming state.

---

# `stream_error`

Example:

```text
event: stream_error
data: {
  "code": "provider_unavailable",
  "message": "..."
}
```

The frontend converts the event into an `ApiError` and exposes a recoverable stream failure to the chat action layer.

---

# `stream_cancelled`

Example:

```text
event: stream_cancelled
data: {
  "message": "..."
}
```

The frontend marks the active stream as cancelled without allowing stale events to modify the current chat.

---

# Concurrency Protection

Streaming is protected at two levels.

## 1. Stream service generation

`ChatStreamService` maintains:

```text
activeStreamId
activeChatId
AbortController
```

Each stream gets a unique stream ID.

A callback is considered current only when:

```text
stream ID matches
AND
controller matches
AND
chat ID matches
AND
request has not been aborted
```

Therefore an old stream cannot update a newer stream.

---

# 2. Chat request controller

```text
frontend/src/features/chat/stream/chat-request-controller.ts
```

The request controller maintains a request generation.

Conceptually:

```text
Request A
   ↓
requestId = 1

Switch / retry / cancel
   ↓
requestId = 2

Request A late event
   ↓
ignored

Request B event
   ↓
accepted
```

This protects against:

* chat A → chat B switching
* chat A → chat B → chat A switching
* retry races
* cancellation races
* delete while streaming
* new chat while streaming
* late source events
* late completion events
* late error events

---

# Chat Session Hydration Protection

Chat history hydration uses a generation counter.

```text
loadChat(A)
    ↓
generation 1

loadChat(B)
    ↓
generation 2

A response arrives late
    ↓
discarded

B response
    ↓
accepted
```

This prevents stale API responses from resurrecting deleted or previously abandoned chat state.

It also protects concurrent `loadChat()` calls for the same chat.

---

# Chat Lifecycle

```text
Create chat
    ↓
Set local chat state
    ↓
Send prompt
    ↓
Stream response
    ↓
Append chunks
    ↓
Receive sources
    ↓
Complete
    ↓
Persisted backend message
```

Session actions support:

```text
create
load
rename
delete
clear active
hydrate
```

---

# Retry Lifecycle

A retry starts a new request generation.

The previous stream is invalidated before the retry begins.

This guarantees:

```text
Old sources ──────X
Old chunks ───────X
Old completion ───X

New sources ───────────► accepted
New chunks ─────────────► accepted
New completion ─────────► accepted
```

This prevents duplicate assistant messages and stale citation metadata.

---

# Citation UI

Component:

```text
src/features/chat/components/citation-sources.tsx
```

Citations are displayed for completed AI messages when:

```text
message.sources?.length > 0
```

They are intentionally hidden while the assistant is still streaming.

---

# Citation Presentation

The citation control is collapsible.

Examples:

```text
1 Source
2 Sources
...
```

Each source displays metadata such as:

```text
Source 1
Page 4
Chunk 2
Relevance 79%
```

Missing metadata is represented safely rather than producing broken UI.

Relevance is derived from vector distance and presented as a bounded percentage.

---

# Citation Accessibility

The citation toggle uses:

```html
<button
  type="button"
  aria-expanded="..."
  aria-controls="..."
>
```

The controlled citation container is hidden when collapsed.

This allows keyboard and assistive-technology users to inspect citation metadata.

---

# Citation Persistence Contract

Citation metadata currently follows this lifecycle:

```text
Backend RAG retrieval
        ↓
SSE `sources` event
        ↓
Chat stream handler
        ↓
Zustand message state
        ↓
Citation UI
```

It is **not currently persisted in the relational `messages` table**.

After a page refresh/re-hydration, message content may remain available while live source metadata may not.

This is an intentional current architecture boundary.

---

# PDF Upload UX

PDF state is tracked per chat.

Lifecycle:

```text
idle
 ↓
validating
 ↓
uploading
 ↓
processing
 ↓
ready
```

Failure transitions into an error state.

The UI supports retrying failed uploads.

The backend enforces file security limits and PDF validation.

---

# Image / Multimodal UX

The frontend supports up to four image attachments.

```text
0 / 4
1 / 4
2 / 4
3 / 4
4 / 4
```

Features include:

* horizontal preview strip
* accessible remove controls
* image count
* payload pairing
* object URL cleanup
* cleanup on component unmount
* cleanup when the active chat changes

---

# Message Rendering

Message bubbles support:

* user messages
* AI messages
* system messages
* multiline content
* copy action
* streaming presentation
* citations
* long-content wrapping

Long unbroken content uses wrapping rules so it does not overflow the viewport.

Multiline content preserves whitespace.

---

# Loading / Error / Empty States

Reusable UI primitives include:

```text
Skeleton
MessageSkeleton
RetryButton
ErrorState
EmptyState
```

Chat history supports:

* loading skeleton
* retry state
* empty history CTA

Streaming failures remain recoverable without corrupting the chat lifecycle.

---

# Responsive Design

The client is hardened for:

```text
mobile
tablet
desktop
```

The chat sidebar uses a mobile drawer.

Composer controls remain usable on small screens.

The application uses dynamic viewport sizing and safe-area-aware bottom spacing.

---

# Accessibility

The production UI includes:

* semantic buttons
* ARIA labels
* ARIA-expanded state
* ARIA-controls
* keyboard navigation
* Escape-to-close sidebar
* focus trapping in mobile drawer
* focus restoration
* reduced-motion handling
* accessible copy controls
* accessible citation controls

---

# Performance

The frontend was audited for:

* unnecessary Zustand subscriptions
* object URL leaks
* streaming render overhead
* excessive bundle dependencies
* image lifecycle cleanup
* responsive layout stability

Production verification included Lighthouse/Core Web Vitals checks.

The production UI target achieved strong performance and accessibility results during the final frontend audit.

---

# Scripts

Defined in `package.json`:

```bash
npm run dev
```

Start the Next.js development server.

```bash
npm run build
```

Create a production build.

```bash
npm run start
```

Start the production Next.js server.

```bash
npm run lint
```

Run ESLint.

```bash
npm run test
```

Run Vitest once.

```bash
npm run test:watch
```

Run Vitest in watch mode.

```bash
npm run test:coverage
```

Run Vitest with coverage.

---

# Testing

The frontend uses:

```text
Vitest
React Testing Library
jsdom
```

The production migration/reliability work includes tests for:

* authentication actions
* attachment handling
* error normalization
* stream transport
* SSE fragmentation
* cancellation
* stale stream rejection
* chat lifecycle races
* hydration races
* citation rendering
* end-to-end citation lifecycle
* chat UX regression
* accessibility semantics

---

# Production Frontend Configuration

Vercel deployment uses:

```text
Root Directory: frontend/
```

The frontend connects directly to the production FastAPI service through:

```text
NEXT_PUBLIC_API_URL
```

Google authentication uses:

```text
NEXT_PUBLIC_GOOGLE_CLIENT_ID
```

No backend secrets belong in the frontend.

---

# Production Routes

The production application exposes the primary routes:

```text
/
 /login
 /signup
 /forgot-password
 /dashboard
```

Authenticated application functionality is centered around the dashboard/chat experience.

---

# Backend Contract

The frontend expects the production FastAPI backend to provide:

```text
Authentication
Chat CRUD
Chat history
AI streaming
PDF upload
RAG retrieval
Structured SSE
Health/readiness
```

The primary AI streaming contract is:

```text
POST /chat/stream
Content-Type: application/json
Accept: text/event-stream
Authorization: Bearer <JWT>
```

---

# Production Baseline

```text
Release:       27882ed
Branch:        main
Framework:     Next.js 16
React:         19
State:         Zustand 5
Status:        GO
```

The frontend is part of the approved production release represented by baseline commit `27882ed`.

---

# Development Rules

When modifying the frontend:

1. Preserve the backend SSE contract.
2. Do not bypass chat request generation guards.
3. Do not allow stale streams to mutate current state.
4. Keep source metadata scoped to the active chat.
5. Preserve authentication boundaries.
6. Do not expose backend secrets.
7. Keep citation rendering presentation-only unless the persistence contract is intentionally changed.
8. Run tests, lint, and production build before merging.

---

# Release Verification

The production release gate verified:

```text
Authentication                 ✅
JWT session state              ✅
Chat creation                  ✅
Chat history                   ✅
Rename / delete                ✅
SSE streaming                  ✅
Cancellation                  ✅
Retry lifecycle                ✅
PDF upload                    ✅
RAG source ingestion           ✅
Citation rendering             ✅
Image attachment support       ✅
Responsive UI                  ✅
Accessibility                  ✅
Production build               ✅
```

**Frontend release status: GO**
