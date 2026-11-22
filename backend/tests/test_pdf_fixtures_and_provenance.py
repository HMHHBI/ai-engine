from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.config import EmbeddingProvider
from app.core.security import create_access_token
from app.db.models import Chat, Document, User, WorkspaceDocument
from app.services.document_ingestion_service import DocumentIngestionService
from app.services.embedding_service import EmbeddingService
from app.services.multi_doc_retrieval import retrieve_multi_document_candidates
from app.utils.pdf_extractor import PDFExtractionError, extract_text_from_pdf
from tests.fixtures.pdf_fixtures import (
    build_academic_paper_pdf,
    build_encrypted_pdf,
    build_image_only_pdf,
    build_sparse_blank_page_pdf,
    build_two_column_pdf,
)


def _normalize_ws(text: str) -> str:
    return " ".join(text.split())


def _create_user(db_session: Session, email: str = "pdf_fixture_tester@example.com") -> User:
    user = User(
        name="PDF Fixture Test User",
        email=email,
        password="test-password-hash",
        is_active=True,
        token_version=1,
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


def _create_workspace(client: TestClient, user: User, name: str) -> int:
    token = create_access_token(user_id=user.id, token_version=user.token_version)
    resp = client.post(
        "/workspaces/",
        headers={"Authorization": f"Bearer {token}"},
        json={"name": name},
    )
    assert resp.status_code == 201, resp.text
    return int(resp.json()["id"])


def test_extracts_text_and_page_boundaries_from_academic_pdf_bytes_and_path(tmp_path: Path) -> None:
    fixture = build_academic_paper_pdf()

    pages_from_bytes = extract_text_from_pdf(fixture.pdf_bytes)
    assert [p.page_number for p in pages_from_bytes] == [1, 2, 3]
    for page_num, marker in fixture.page_markers.items():
        extracted = next(p.text for p in pages_from_bytes if p.page_number == page_num)
        assert marker in _normalize_ws(extracted)

    pdf_file = tmp_path / fixture.filename
    pdf_file.write_bytes(fixture.pdf_bytes)
    pages_from_path = extract_text_from_pdf(pdf_file)
    assert pages_from_path == pages_from_bytes


def test_preserves_true_page_numbers_when_intermediate_page_is_blank() -> None:
    fixture = build_sparse_blank_page_pdf()
    pages = extract_text_from_pdf(fixture.pdf_bytes)

    assert len(pages) == 2
    assert [p.page_number for p in pages] == [1, 3]
    assert fixture.page_markers[1] in _normalize_ws(pages[0].text)
    assert fixture.page_markers[3] in _normalize_ws(pages[1].text)


def test_extracts_two_column_pdf_content() -> None:
    pdf_bytes = build_two_column_pdf()
    pages = extract_text_from_pdf(pdf_bytes)

    assert len(pages) == 1
    assert pages[0].page_number == 1
    extracted = pages[0].text
    assert "Left Column Section:" in extracted
    assert "Neuromorphic spiking cores" in extracted
    assert "Right Column Section:" in extracted
    assert "Tensor accelerators sustain" in extracted


@pytest.mark.parametrize(
    ("bad_payload", "expected_message"),
    [
        (b"not-a-pdf", "The uploaded file is not a valid PDF."),
        (b"%PDF-1.7\ncorrupted-binary-stream", "The uploaded PDF is invalid or corrupted."),
        (build_image_only_pdf(), "No readable text was found in this PDF."),
        (build_encrypted_pdf(), "Password-protected PDFs are not supported."),
    ],
)
def test_rejects_unreadable_or_invalid_pdfs_deterministically(
    bad_payload: bytes,
    expected_message: str,
) -> None:
    with pytest.raises(PDFExtractionError, match=expected_message):
        extract_text_from_pdf(bad_payload)


def test_chunk_text_from_extracted_pdf_never_crosses_page_boundaries() -> None:
    fixture = build_academic_paper_pdf()
    pages = extract_text_from_pdf(fixture.pdf_bytes)

    chunks = EmbeddingService.chunk_text(pages, chunk_size=140, overlap=20)
    assert len(chunks) >= 3

    text_by_page = {p.page_number: _normalize_ws(p.text) for p in pages}
    for idx, chunk in enumerate(chunks):
        assert chunk.chunk_index == idx
        assert chunk.page_number in text_by_page
        first_word = chunk.text.split()[0]
        assert first_word in text_by_page[chunk.page_number]


@pytest.mark.asyncio
async def test_end_to_end_pdf_ingestion_and_retrieval_preserves_citation_provenance(
    client: TestClient,
    db_session: Session,
) -> None:
    user = _create_user(db_session)
    workspace_id = _create_workspace(client, user, "Phase 2D PDF Provenance Workspace")

    paper_a = build_academic_paper_pdf(
        paper_id="PAPER-A",
        title="Hybrid Vector Retrieval Architecture",
        methodology_phrase="HNSW pgvector cosine indexing with 768-dimensional embeddings",
        findings_phrase="p95 retrieval latency dropped by 43 percent across 5000 chunks",
    )
    paper_b = build_academic_paper_pdf(
        paper_id="PAPER-B",
        title="Neuromorphic Edge Inference",
        methodology_phrase="spiking event-driven crossbar arrays with local SRAM",
        findings_phrase="energy per inference improved by 61 percent on edge workloads",
    )

    docs: list[Document] = []
    for paper in (paper_a, paper_b):
        chat = Chat(user_id=user.id, title=f"Chat for {paper.filename}")
        db_session.add(chat)
        db_session.commit()
        db_session.refresh(chat)

        doc = Document(
            user_id=user.id,
            chat_id=chat.id,
            filename=paper.filename,
            mime_type="application/pdf",
            status="processing",
        )
        db_session.add(doc)
        db_session.commit()
        db_session.refresh(doc)

        extracted_pages = extract_text_from_pdf(paper.pdf_bytes)
        deterministic_vec = [0.02] * 768

        with patch.object(
            EmbeddingService,
            "generate_embedding",
            new=AsyncMock(return_value=deterministic_vec),
        ):
            ingest_summary = await DocumentIngestionService.ingest(
                user_id=user.id,
                document_id=doc.id,
                pages=extracted_pages,
                embedding_provider=EmbeddingProvider.OLLAMA,
            )

        assert ingest_summary["page_count"] == 3
        assert ingest_summary["chunks_indexed"] >= 3

        doc.status = "ready"
        doc.page_count = ingest_summary["page_count"]
        db_session.add(
            WorkspaceDocument(
                workspace_id=workspace_id,
                document_id=doc.id,
                added_by=user.id,
            )
        )
        db_session.commit()
        db_session.refresh(doc)
        docs.append(doc)

    doc_a, doc_b = docs
    query_vec = [0.02] * 768

    with patch.object(
        EmbeddingService,
        "generate_embedding",
        new=AsyncMock(return_value=query_vec),
    ):
        evidence = await retrieve_multi_document_candidates(
            db_session,
            workspace_id=workspace_id,
            requester_id=user.id,
            document_ids=[doc_a.id, doc_b.id],
            query="What methodology and p95 latency findings were reported?",
            candidate_limit=10,
        )

    assert len(evidence) >= 2
    evidence_by_doc: dict[int, list[dict]] = {}
    for item in evidence:
        doc_id = int(item["document_id"])
        evidence_by_doc.setdefault(doc_id, []).append(item)
        assert item["page_number"] in (1, 2, 3)
        assert isinstance(item["chunk_index"], int)
        text_val = item.get("content", "")
        assert text_val

    assert doc_a.id in evidence_by_doc
    assert doc_b.id in evidence_by_doc

    doc_a_pages_and_text = [
        (e["page_number"], _normalize_ws(e.get("content", "")))
        for e in evidence_by_doc[doc_a.id]
    ]
    assert any(
        page == 2 and "HNSW pgvector cosine indexing" in text
        for page, text in doc_a_pages_and_text
    )
    assert any(
        page == 3 and "p95 retrieval latency dropped by 43 percent" in text
        for page, text in doc_a_pages_and_text
    )
