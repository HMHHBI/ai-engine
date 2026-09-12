#!/usr/bin/env python3
"""
Generate deterministic synthetic PDF fixtures for P3-04 retrieval evaluation.

These documents are intentionally synthetic and version-controlled. They are
designed to exercise retrieval across:

    - semantic queries
    - exact terminology
    - identifiers
    - numeric values
    - abbreviations
    - multi-hop retrieval

The generated PDFs are evaluation fixtures only. They contain no customer data.
"""

from __future__ import annotations

from pathlib import Path

import fitz


FIXTURE_DIR = (
    Path(__file__).resolve().parent
    / "fixtures"
    / "retrieval_quality"
)

PAGE_WIDTH = 595
PAGE_HEIGHT = 842

LEFT_MARGIN = 50
RIGHT_MARGIN = 50
TOP_MARGIN = 50
BOTTOM_MARGIN = 50

TITLE_FONT_SIZE = 18
HEADING_FONT_SIZE = 12
BODY_FONT_SIZE = 10
BODY_LINE_HEIGHT = 1.35

SECTION_SPACING = 18
HEADING_SPACING = 8
TITLE_SPACING = 28


DOCUMENTS = {
    "production_rag_spec.pdf": [
        (
            "Production RAG Specification",
            [
                (
                    "Retrieval Architecture",
                    (
                        "The production retrieval pipeline uses query embeddings and "
                        "PostgreSQL pgvector to locate relevant document chunks. A chat "
                        "request is authenticated before document ownership is resolved. "
                        "The retriever receives the authenticated user ID, document ID, "
                        "query vector, and requested top-K value. Retrieval is scoped to "
                        "the requested document and authenticated user."
                    ),
                ),
                (
                    "Dense Retrieval",
                    (
                        "Dense retrieval compares the query embedding with stored chunk "
                        "embeddings using cosine distance. Candidates are ordered by "
                        "ascending distance. The production retriever applies a best "
                        "distance threshold of 0.70 and an adaptive margin of 0.15. "
                        "The adaptive limit is the smaller of the best observed distance "
                        "plus the margin and the maximum allowed distance."
                    ),
                ),
                (
                    "Candidate Limits",
                    (
                        "The retriever accepts a top-K value from 1 through 50. The "
                        "application normally requests a small candidate set because "
                        "retrieval quality must be balanced against context size and "
                        "downstream processing cost. The final result count can be lower "
                        "than the requested top-K value when adaptive distance filtering "
                        "removes weak matches."
                    ),
                ),
                (
                    "Document Isolation",
                    (
                        "Document retrieval must preserve the authenticated ownership "
                        "boundary. A document ID is not an authorization credential. "
                        "Candidate queries must constrain the document relationship and "
                        "the owning user relationship. Retrieval must not obtain broad "
                        "cross-tenant candidates and filter them only after retrieval."
                    ),
                ),
                (
                    "Context Construction",
                    (
                        "Retrieved chunks are converted into context for the language "
                        "model. Chunk ordering and document identity remain available "
                        "during context construction. The retrieval layer is responsible "
                        "for returning only chunks that satisfy its ownership and "
                        "distance constraints."
                    ),
                ),
                (
                    "Evaluation Metrics",
                    (
                        "Retrieval quality is evaluated using Hit Rate at K, Mean "
                        "Reciprocal Rank, Context Precision at K, and Context Recall at K. "
                        "Primary evaluation uses K equal to 5, while K values of 1, 3, 5, "
                        "and 10 provide ranking and recall characterization. Golden "
                        "queries identify one or more relevant chunk IDs."
                    ),
                ),
                (
                    "Failure Modes",
                    (
                        "A retrieval failure can occur when the relevant chunk is absent "
                        "from the returned candidate set, ranked too low, or rejected by "
                        "the configured distance threshold. Evaluation should distinguish "
                        "retrieval misses from downstream generation failures. A low "
                        "retrieval score should not automatically be interpreted as an "
                        "LLM quality problem."
                    ),
                ),
                (
                    "Hybrid Retrieval Evaluation",
                    (
                        "Hybrid retrieval combines lexical and dense signals to test "
                        "whether exact terminology and semantic similarity provide "
                        "complementary evidence. Lexical retrieval is particularly useful "
                        "for identifiers, version strings, error codes, and exact terms, "
                        "while dense retrieval can improve meaning-level matching."
                    ),
                ),
                (
                    "Reranking Evaluation",
                    (
                        "A reranker may reorder an initial candidate set using richer "
                        "query-document relevance features. Evaluation must compare "
                        "dense retrieval, lexical retrieval, hybrid retrieval, dense "
                        "retrieval with reranking, and hybrid retrieval with reranking "
                        "using the same golden query set. Reranking must not weaken "
                        "document ownership or tenant-isolation guarantees."
                    ),
                ),
                (
                    "Production Decision Criteria",
                    (
                        "A retrieval architecture should be selected using quality, "
                        "latency, reliability, and security evidence rather than a single "
                        "metric. Improvements in recall are not sufficient if latency or "
                        "isolation guarantees regress. The evaluation framework therefore "
                        "records ranking metrics, failure modes, and retrieval latency "
                        "before recommending a production configuration."
                    ),
                ),
            ],
        ),
    ],
    "api_platform_reference.pdf": [
        (
            "API Platform Reference",
            [
                (
                    "Authentication and Authorization",
                    (
                        "The API uses bearer-token authentication. Every protected "
                        "request must include an Authorization header containing a "
                        "valid access token. Access tokens are validated before "
                        "application handlers execute. Authentication establishes "
                        "the caller identity, while authorization determines whether "
                        "that identity may access the requested resource."
                    ),
                ),
                (
                    "API Versioning",
                    (
                        "The current stable API version is v2. Requests to the "
                        "versioned API must use the /api/v2/ path prefix. The legacy "
                        "v1 interface remains available only for compatibility "
                        "testing and should not be used for new integrations. "
                        "Version negotiation is explicit rather than inferred."
                    ),
                ),
                (
                    "Request IDs",
                    (
                        "Every accepted API request receives a request ID. The "
                        "request ID is returned through the X-Request-ID response "
                        "header and is included in structured application logs. "
                        "Clients should preserve the request ID when reporting "
                        "failures because it allows operators to correlate the "
                        "request with backend logs and upstream events."
                    ),
                ),
                (
                    "Timeout Policy",
                    (
                        "The API gateway uses a 60 second external API timeout. "
                        "The PostgreSQL query timeout is 30 seconds. Redis operations "
                        "have a 5 second timeout. These limits are intentionally "
                        "different because database, cache, and external service "
                        "operations have different expected latency profiles."
                    ),
                ),
                (
                    "Pagination",
                    (
                        "Collection endpoints use cursor-based pagination. The "
                        "default page size is 50 records and the maximum permitted "
                        "page size is 200 records. A response contains next_cursor "
                        "when additional records are available. Clients should not "
                        "assume that an empty page means the collection is exhausted "
                        "unless next_cursor is absent."
                    ),
                ),
                (
                    "Streaming",
                    (
                        "Streaming responses use Server-Sent Events, abbreviated "
                        "SSE. An SSE stream is established over HTTP and emits "
                        "ordered events until completion or cancellation. The "
                        "client must keep the connection open while events are "
                        "being received and should treat a transport disconnect "
                        "as a recoverable stream failure when the request is "
                        "otherwise safe to retry."
                    ),
                ),
                (
                    "Redis Integration",
                    (
                        "Redis is used for short-lived control-plane state, rate "
                        "limiting, and selected request coordination. Redis "
                        "connections are obtained from the configured asynchronous "
                        "client pool. A Redis timeout is five seconds. Redis is "
                        "not the authoritative source for persistent document "
                        "content."
                    ),
                ),
                (
                    "PostgreSQL Integration",
                    (
                        "PostgreSQL is the authoritative relational datastore for "
                        "users, chats, documents, messages, and document chunks. "
                        "Vector retrieval is implemented with pgvector inside "
                        "PostgreSQL. Database operations must respect the "
                        "authenticated user's ownership boundary."
                    ),
                ),
                (
                    "Error Handling",
                    (
                        "HTTP 400 indicates an invalid client request. HTTP 401 "
                        "indicates that authentication is missing or invalid. "
                        "HTTP 403 indicates that authentication succeeded but the "
                        "caller is not authorized to access the requested resource. "
                        "HTTP 404 indicates that the requested resource does not "
                        "exist or is intentionally not exposed to the caller."
                    ),
                ),
            ],
        ),
    ],
    "operations_runbook.pdf": [
        (
            "Operations Runbook",
            [
                (
                    "Pre-deployment Checks",
                    (
                        "Before deployment, verify that the target revision is "
                        "known, database migrations are compatible, required "
                        "environment variables are present, and the health "
                        "endpoint can be reached. Production deployment should "
                        "not proceed when a required secret, database connection, "
                        "or dependency is unavailable."
                    ),
                ),
                (
                    "Health Checks",
                    (
                        "The liveness check determines whether the application "
                        "process is running. The readiness check verifies that "
                        "required infrastructure is available before traffic is "
                        "accepted. Readiness therefore provides a stronger "
                        "signal than liveness for routing decisions."
                    ),
                ),
                (
                    "Rate Limits",
                    (
                        "Application rate limits protect shared resources from "
                        "unbounded request volume. Rate-limit decisions are "
                        "enforced before expensive downstream work whenever "
                        "possible. Redis-backed counters are used for distributed "
                        "rate-limit state. A rejected request should not consume "
                        "the downstream AI or document-processing capacity."
                    ),
                ),
                (
                    "Timeouts and Retries",
                    (
                        "Timeouts define the maximum time an operation may consume "
                        "before it is considered failed. Retries should be limited "
                        "to operations that are safe to retry. Repeating a request "
                        "after a timeout can amplify load if the original operation "
                        "continues running, so retry policy must account for "
                        "downstream capacity."
                    ),
                ),
                (
                    "Capacity Baseline",
                    (
                        "The operational baseline records throughput, latency, "
                        "error rate, concurrency, and resource saturation. A "
                        "measured throughput increase is not automatically a "
                        "capacity improvement when external dependencies or "
                        "event-loop saturation are the limiting factors."
                    ),
                ),
                (
                    "Monitoring",
                    (
                        "Operational monitoring should track request latency, "
                        "HTTP error rates, database pool utilization, Redis "
                        "availability, embedding failures, AI upstream failures, "
                        "and streaming disconnects. Metrics should be correlated "
                        "with deployment revision and request ID where available."
                    ),
                ),
                (
                    "Incident Response",
                    (
                        "During an incident, first establish the affected service "
                        "boundary and approximate start time. Preserve request IDs, "
                        "deployment version, relevant metrics, and representative "
                        "error messages. Avoid making unrelated configuration "
                        "changes before the primary failure mode is identified."
                    ),
                ),
                (
                    "Failure Handling",
                    (
                        "A failed document ingestion operation must not leave a "
                        "partially indexed document that appears ready. Embedding "
                        "failure is treated as an ingestion failure. Vector "
                        "replacement is expected to be atomic so that an existing "
                        "indexed document is not replaced by an incomplete set "
                        "of chunks."
                    ),
                ),
                (
                    "Rollback",
                    (
                        "Rollback should restore the last known-good application "
                        "revision when a deployment introduces a confirmed "
                        "application regression. Database rollback is a separate "
                        "decision and must not be assumed to be safe merely because "
                        "the application revision was rolled back."
                    ),
                ),
            ],
        ),
    ],
    "security_architecture.pdf": [
        (
            "Security Architecture",
            [
                (
                    "Identity Verification",
                    (
                        "Authentication establishes the identity associated with "
                        "an API request. Access tokens must be validated before "
                        "protected resources are accessed. Invalid or expired "
                        "credentials must not reach resource-level authorization "
                        "logic as if they represented a valid identity."
                    ),
                ),
                (
                    "Authorization",
                    (
                        "Authorization determines whether an authenticated user "
                        "may perform an operation against a resource. A valid "
                        "identity alone does not grant access to every document, "
                        "chat, message, or vector belonging to another user."
                    ),
                ),
                (
                    "Tenant Isolation",
                    (
                        "Tenant isolation requires every document retrieval path "
                        "to preserve the authenticated user's ownership boundary. "
                        "Document identifiers are not authorization credentials. "
                        "A caller who knows another user's document ID must still "
                        "be unable to retrieve that document."
                    ),
                ),
                (
                    "Document Ownership",
                    (
                        "A document is owned by a user and associated with a chat. "
                        "Ownership validation should verify the document user "
                        "relationship and the owning chat's user relationship. "
                        "Both relationships are relevant because the chat is part "
                        "of the document ownership chain."
                    ),
                ),
                (
                    "IDOR Protection",
                    (
                        "Insecure direct object reference, or IDOR, occurs when "
                        "an attacker can substitute another object's identifier "
                        "and receive that object without an authorization check. "
                        "Document IDs, chat IDs, and message IDs must therefore "
                        "always be resolved within the authenticated ownership "
                        "boundary."
                    ),
                ),
                (
                    "Session Access",
                    (
                        "Session state must not be treated as proof that a caller "
                        "owns an arbitrary resource identifier. Authentication "
                        "provides the principal identity, while authorization "
                        "checks determine whether that principal may access "
                        "the requested resource."
                    ),
                ),
                (
                    "Audit Logging",
                    (
                        "Security-relevant events should contain sufficient "
                        "structured context to support investigation. Request "
                        "IDs, user identifiers where appropriate, resource IDs, "
                        "operation names, and failure classifications may be "
                        "recorded without storing secrets or access tokens."
                    ),
                ),
                (
                    "Least Privilege",
                    (
                        "Services and database operations should use the minimum "
                        "privileges necessary for their function. Evaluation "
                        "workloads should use an isolated test database rather "
                        "than credentials capable of modifying production data."
                    ),
                ),
                (
                    "Data Boundary",
                    (
                        "Vector search is part of the protected document-data "
                        "boundary. Candidate generation must respect ownership "
                        "constraints rather than retrieving a broad set of "
                        "cross-tenant candidates and filtering them afterward."
                    ),
                ),
            ],
        ),
    ],
    "incident_postmortem.pdf": [
        (
            "Incident INC-4821",
            [
                (
                    "Incident Summary",
                    (
                        "Incident INC-4821 occurred on 2026-08-18 after deployment "
                        "revision rel-2026.08.18. The primary symptom was elevated "
                        "API latency during concurrent document-processing traffic. "
                        "The first alert was recorded at 14:05 UTC and service "
                        "recovery was confirmed at 14:37 UTC."
                    ),
                ),
                (
                    "Observed Metrics",
                    (
                        "During the incident, p95 API latency increased from "
                        "420 milliseconds to 3.8 seconds. Database CPU remained "
                        "below 65 percent while application event-loop utilization "
                        "approached saturation. Redis latency remained within its "
                        "normal operating range."
                    ),
                ),
                (
                    "Root Cause",
                    (
                        "The root cause was event-loop contention caused by a "
                        "synchronous operation executing in an asynchronous request "
                        "path. The operation increased event-loop occupancy under "
                        "concurrency even though PostgreSQL and Redis were not "
                        "resource-saturated."
                    ),
                ),
                (
                    "Mitigation",
                    (
                        "The immediate mitigation was to reduce concurrent "
                        "processing and roll traffic back to the previous stable "
                        "application revision. The service returned to the normal "
                        "latency envelope after concurrency was reduced."
                    ),
                ),
            ],
        ),
        (
            "Incident INC-4812",
            [
                (
                    "Incident Summary",
                    (
                        "Incident INC-4812 affected document ingestion on "
                        "2026-08-11. Requests remained authenticated and API "
                        "routing was healthy, but a subset of PDF ingestion jobs "
                        "failed during embedding generation. The first alert "
                        "was recorded at 09:42 UTC."
                    ),
                ),
                (
                    "Observed Metrics",
                    (
                        "Embedding failure rate reached 18 percent for the "
                        "affected workload. PDF extraction succeeded for the "
                        "failed jobs, while the embedding provider returned "
                        "upstream timeout responses. PostgreSQL transaction "
                        "latency remained normal."
                    ),
                ),
                (
                    "Root Cause",
                    (
                        "The root cause was upstream embedding-provider timeout "
                        "behavior combined with a workload that exceeded the "
                        "effective embedding concurrency budget. The application "
                        "correctly rejected incomplete embedding results rather "
                        "than marking partially indexed documents as ready."
                    ),
                ),
                (
                    "Corrective Action",
                    (
                        "The corrective action was to retain bounded embedding "
                        "concurrency, preserve atomic vector replacement, and "
                        "measure provider latency separately from database and "
                        "HTTP capacity."
                    ),
                ),
            ],
        ),
        (
            "Incident INC-4827",
            [
                (
                    "Incident Summary",
                    (
                        "Incident INC-4827 occurred during an API client migration "
                        "from v1 to v2. The application remained available, but "
                        "some clients received HTTP 404 responses because they "
                        "continued sending requests to the retired v1 route."
                    ),
                ),
                (
                    "Observed Metrics",
                    (
                        "The 404 response rate increased to 11 percent for the "
                        "affected client population. Authenticated requests to "
                        "the v2 endpoint continued to succeed. Database and "
                        "Redis health metrics were normal throughout the event."
                    ),
                ),
                (
                    "Root Cause",
                    (
                        "The root cause was an incomplete client migration. The "
                        "backend was operating according to the published v2 "
                        "routing contract, but one integration had not updated "
                        "its API base path."
                    ),
                ),
                (
                    "Corrective Action",
                    (
                        "The corrective action was to update the affected client, "
                        "add explicit API-version compatibility checks to the "
                        "integration test suite, and document the v1 retirement "
                        "timeline."
                    ),
                ),
            ],
        ),
    ],
}


def add_section(
    page: fitz.Page,
    heading: str,
    body: str,
    y: float,
) -> float:
    """Render one section and return the next vertical position."""
    page.insert_text(
        (LEFT_MARGIN, y),
        heading,
        fontsize=HEADING_FONT_SIZE,
        fontname="helv",
    )

    y += HEADING_FONT_SIZE + HEADING_SPACING

    body_rect = fitz.Rect(
        LEFT_MARGIN,
        y,
        PAGE_WIDTH - RIGHT_MARGIN,
        PAGE_HEIGHT - BOTTOM_MARGIN,
    )

    result = page.insert_textbox(
        body_rect,
        body,
        fontsize=BODY_FONT_SIZE,
        fontname="helv",
        lineheight=BODY_LINE_HEIGHT,
    )

    if result < 0:
        raise RuntimeError(
            f"Text overflow while rendering section '{heading}'."
        )

    rendered_height = body_rect.height - result

    return (
        y
        + rendered_height
        + SECTION_SPACING
    )


def generate_document(
    filename: str,
    pages: list[tuple[str, list[tuple[str, str]]]],
) -> Path:
    output_path = FIXTURE_DIR / filename

    document = fitz.open()

    try:
        page = document.new_page(
            width=PAGE_WIDTH,
            height=PAGE_HEIGHT,
        )

        y = TOP_MARGIN

        for document_title, sections in pages:
            page.insert_text(
                (LEFT_MARGIN, y),
                document_title,
                fontsize=TITLE_FONT_SIZE,
                fontname="helv",
            )

            y += TITLE_FONT_SIZE + TITLE_SPACING

            for heading, body in sections:
                estimated_body_height = (
                    len(body) / 78
                ) * BODY_FONT_SIZE * BODY_LINE_HEIGHT

                estimated_section_height = (
                    HEADING_FONT_SIZE
                    + HEADING_SPACING
                    + estimated_body_height
                    + SECTION_SPACING
                )

                available_height = (
                    PAGE_HEIGHT
                    - BOTTOM_MARGIN
                    - y
                )

                if (
                    estimated_section_height
                    > available_height
                    and y > TOP_MARGIN + 20
                ):
                    page = document.new_page(
                        width=PAGE_WIDTH,
                        height=PAGE_HEIGHT,
                    )

                    y = TOP_MARGIN

                y = add_section(
                    page,
                    heading,
                    body,
                    y,
                )

                if y > PAGE_HEIGHT - BOTTOM_MARGIN:
                    page = document.new_page(
                        width=PAGE_WIDTH,
                        height=PAGE_HEIGHT,
                    )

                    y = TOP_MARGIN

        document.save(
            output_path,
            garbage=4,
            deflate=True,
        )

    finally:
        document.close()

    return output_path


def validate_generated_pdf(
    path: Path,
) -> None:
    """Validate that the generated PDF contains readable text."""
    with fitz.open(path) as document:
        if len(document) == 0:
            raise RuntimeError(
                f"Generated PDF has no pages: {path}"
            )

        text_length = sum(
            len(page.get_text())
            for page in document
        )

        if text_length == 0:
            raise RuntimeError(
                f"Generated PDF contains no extractable text: {path}"
            )


def main() -> None:
    """Generate all deterministic retrieval evaluation fixtures."""
    FIXTURE_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    generated: list[Path] = []

    for filename, pages in DOCUMENTS.items():
        output_path = generate_document(
            filename,
            pages,
        )

        validate_generated_pdf(
            output_path
        )

        generated.append(
            output_path
        )

    print("=" * 72)
    print("P3-04 RETRIEVAL QUALITY FIXTURE GENERATION")
    print("=" * 72)
    print(f"Output directory: {FIXTURE_DIR}")
    print()

    for path in generated:
        with fitz.open(path) as document:
            text_length = sum(
                len(page.get_text())
                for page in document
            )

            print(
                f"{path.name}: "
                f"{len(document)} page(s), "
                f"{path.stat().st_size} bytes, "
                f"{text_length} extracted characters"
            )

    print()
    print(
        "Generated and validated synthetic evaluation fixtures successfully."
    )


if __name__ == "__main__":
    main()
