#!/usr/bin/env python3
"""
Seed the isolated P3-04 retrieval evaluation database.

Pipeline:

    Synthetic PDF
        ↓
    production PDF extractor
        ↓
    DocumentIngestionService
        ↓
    EmbeddingService.chunk_text()
        ↓
    EmbeddingService.generate_embedding()
        ↓
    VectorRepository.replace_document_chunks()
        ↓
    PostgreSQL / pgvector
        ↓
    chunk manifest

The script refuses to run unless TEST_DATABASE_URL points to a database
whose name clearly identifies it as a test database.

No production database should ever be used by this script.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

from sqlalchemy import create_engine, delete, select
from sqlalchemy.orm import Session, sessionmaker

import app.db.session as app_session_module
from app.core.config import EmbeddingProvider, settings
from app.db.models import Chat, Document, DocumentChunk, User
from app.repositories.document_repo import DocumentRepository
from app.services.document_ingestion_service import DocumentIngestionService
from app.utils.pdf_extractor import extract_text_from_pdf


DEFAULT_FIXTURE_DIR = (
    Path(__file__).resolve().parent
    / "fixtures"
    / "retrieval_quality"
)

DEFAULT_MANIFEST = (
    Path(__file__).resolve().parent
    / "retrieval_quality_chunk_manifest.json"
)

EVALUATION_USER_EMAIL = "p3-04-retrieval-eval@example.invalid"
EVALUATION_USER_NAME = "P3-04 Retrieval Evaluation"

EVALUATION_CHAT_TITLE = "P3-04 Retrieval Evaluation Corpus"

FIXTURE_FILENAMES = (
    "production_rag_spec.pdf",
    "api_platform_reference.pdf",
    "operations_runbook.pdf",
    "security_architecture.pdf",
    "incident_postmortem.pdf",
)


def assert_test_database(url: str | None) -> None:
    """Refuse to run against a non-test database."""
    if not url:
        raise RuntimeError(
            "TEST_DATABASE_URL is required. "
            "The retrieval evaluation seeder will not run "
            "without an explicit test database."
        )

    parsed = urlparse(url)

    database_name = (
        parsed.path or ""
    ).lstrip("/").split("?", 1)[0]

    if not database_name:
        raise RuntimeError(
            "TEST_DATABASE_URL does not contain a database name."
        )

    normalized_name = database_name.lower()

    is_test_database = (
        normalized_name.endswith("_test")
        or normalized_name.startswith("test_")
        or normalized_name == "test"
        or "_test_" in normalized_name
    )

    if not is_test_database:
        raise RuntimeError(
            "CRITICAL SAFETY VIOLATION: "
            "TEST_DATABASE_URL must point to a dedicated test database. "
            f"Received database '{database_name}'."
        )


def build_evaluation_engine(database_url: str):
    """Build a database engine for the isolated evaluation database."""
    return create_engine(
        database_url,
        connect_args={
            "options": "-c client_encoding=utf8",
        },
        pool_pre_ping=True,
    )


def get_or_create_evaluation_identity(
    session: Session,
) -> tuple[int, int]:
    """
    Get or create the deterministic evaluation user and chat.

    The identity is isolated by a reserved .invalid email address and a
    dedicated evaluation chat title.
    """
    user = session.execute(
        select(User).where(
            User.email == EVALUATION_USER_EMAIL,
        )
    ).scalar_one_or_none()

    if user is None:
        user = User(
            name=EVALUATION_USER_NAME,
            email=EVALUATION_USER_EMAIL,
            password="P3-04-EVALUATION-ONLY",
            is_active=True,
        )
        session.add(user)
        session.flush()

    chat = session.execute(
        select(Chat).where(
            Chat.user_id == user.id,
            Chat.title == EVALUATION_CHAT_TITLE,
        )
    ).scalar_one_or_none()

    if chat is None:
        chat = Chat(
            user_id=user.id,
            title=EVALUATION_CHAT_TITLE,
            persona="default",
            ai_provider=None,
            ai_model=None,
            embedding_provider=settings.DEFAULT_EMBEDDING_PROVIDER.value,
        )
        session.add(chat)
        session.flush()

    return user.id, chat.id


def remove_previous_fixture_documents(
    session: Session,
    *,
    user_id: int,
    chat_id: int,
) -> None:
    """
    Remove only documents belonging to this evaluation identity and corpus.

    No other user's documents are touched.
    """
    existing_documents = list(
        session.execute(
            select(Document).where(
                Document.user_id == user_id,
                Document.chat_id == chat_id,
                Document.filename.in_(FIXTURE_FILENAMES),
            )
        ).scalars()
    )

    for document in existing_documents:
        session.delete(document)

    session.flush()


def create_document(
    session: Session,
    *,
    user_id: int,
    chat_id: int,
    filename: str,
    file_size: int,
    page_count: int,
) -> int:
    """Create a processing document and return its database ID."""
    document = Document(
        user_id=user_id,
        chat_id=chat_id,
        filename=filename,
        mime_type="application/pdf",
        file_size=file_size,
        page_count=page_count,
        storage_url=None,
        status="processing",
        error_message=None,
    )

    session.add(document)
    session.flush()

    return document.id


def fetch_manifest_rows(
    session: Session,
    *,
    user_id: int,
    document_id: int,
) -> list[dict]:
    """Read actual database-generated chunk IDs and metadata."""
    rows = session.execute(
        select(
            DocumentChunk.id,
            DocumentChunk.document_id,
            DocumentChunk.chat_id,
            DocumentChunk.chunk_index,
            DocumentChunk.page_number,
            DocumentChunk.content,
        )
        .join(
            Document,
            Document.id == DocumentChunk.document_id,
        )
        .join(
            Chat,
            Chat.id == Document.chat_id,
        )
        .where(
            DocumentChunk.document_id == document_id,
            Document.user_id == user_id,
            Chat.user_id == user_id,
        )
        .order_by(
            DocumentChunk.chunk_index.asc(),
            DocumentChunk.id.asc(),
        )
    ).all()

    manifest_rows: list[dict] = []

    for row in rows:
        manifest_rows.append(
            {
                "chunk_id": row.id,
                "document_id": row.document_id,
                "chat_id": row.chat_id,
                "chunk_index": row.chunk_index,
                "page_number": row.page_number,
                "content": row.content,
            }
        )

    return manifest_rows


def validate_manifest_rows(
    rows: list[dict],
    *,
    document_id: int,
) -> None:
    """Validate the generated chunk manifest before writing it."""
    if not rows:
        raise RuntimeError(
            f"Document {document_id} produced zero database chunks."
        )

    chunk_ids = [
        row["chunk_id"]
        for row in rows
    ]

    chunk_indexes = [
        row["chunk_index"]
        for row in rows
    ]

    if len(chunk_ids) != len(set(chunk_ids)):
        raise RuntimeError(
            f"Document {document_id} produced duplicate chunk IDs."
        )

    if len(chunk_indexes) != len(set(chunk_indexes)):
        raise RuntimeError(
            f"Document {document_id} produced duplicate chunk indexes."
        )

    expected_indexes = list(
        range(
            len(chunk_indexes)
        )
    )

    if chunk_indexes != expected_indexes:
        raise RuntimeError(
            f"Document {document_id} chunk indexes are not deterministic "
            f"zero-based sequence: {chunk_indexes}"
        )

    for row in rows:
        if row["document_id"] != document_id:
            raise RuntimeError(
                f"Manifest row {row['chunk_id']} belongs to "
                f"document {row['document_id']}, expected {document_id}."
            )

        if not row["content"].strip():
            raise RuntimeError(
                f"Manifest row {row['chunk_id']} contains empty content."
            )

        if len(row["content"]) > 500:
            raise RuntimeError(
                f"Manifest row {row['chunk_id']} exceeds the production "
                f"500-character chunk ceiling."
            )


def write_manifest(
    path: Path,
    *,
    test_database_name: str,
    provider: str,
    documents: list[dict],
) -> None:
    """Write the complete machine-readable retrieval corpus manifest."""
    payload = {
        "version": "1.0",
        "evaluation": "P3-04 hybrid retrieval and reranking",
        "generated_at": datetime.now(
            timezone.utc
        ).isoformat(),
        "database": test_database_name,
        "embedding_provider": provider,
        "chunking": {
            "chunk_size": 500,
            "overlap": 50,
            "source": "DocumentIngestionService",
        },
        "documents": documents,
    }

    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    with path.open(
        "w",
        encoding="utf-8",
    ) as handle:
        json.dump(
            payload,
            handle,
            indent=2,
            ensure_ascii=False,
        )


async def seed(
    *,
    fixture_dir: Path,
    manifest_path: Path,
) -> None:
    """Execute the complete isolated corpus seeding workflow."""
    test_database_url = os.getenv(
        "TEST_DATABASE_URL"
    )

    assert_test_database(
        test_database_url
    )

    fixture_paths = [
        fixture_dir / filename
        for filename in FIXTURE_FILENAMES
    ]

    missing = [
        str(path)
        for path in fixture_paths
        if not path.is_file()
    ]

    if missing:
        raise FileNotFoundError(
            "Missing retrieval fixture PDFs:\n"
            + "\n".join(missing)
        )

    evaluation_engine = build_evaluation_engine(
        test_database_url
    )

    EvaluationSessionLocal = sessionmaker(
        bind=evaluation_engine,
        autoflush=False,
        expire_on_commit=False,
    )

    original_bind = app_session_module.SessionLocal.kw.get(
        "bind"
    )

    provider = (
        settings.DEFAULT_EMBEDDING_PROVIDER
    )

    if not isinstance(
        provider,
        EmbeddingProvider,
    ):
        raise RuntimeError(
            "settings.DEFAULT_EMBEDDING_PROVIDER is not a valid "
            "EmbeddingProvider."
        )

    try:
        app_session_module.SessionLocal.configure(
            bind=evaluation_engine
        )

        with EvaluationSessionLocal() as session:
            user_id, chat_id = get_or_create_evaluation_identity(
                session
            )

            remove_previous_fixture_documents(
                session,
                user_id=user_id,
                chat_id=chat_id,
            )

            session.commit()

        document_entries: list[dict] = []

        for fixture_path in fixture_paths:
            print()
            print("=" * 72)
            print(f"Processing: {fixture_path.name}")
            print("=" * 72)

            pages = await asyncio.to_thread(
                extract_text_from_pdf,
                fixture_path,
            )

            if not pages:
                raise RuntimeError(
                    f"No readable pages extracted from {fixture_path.name}."
                )

            file_size = fixture_path.stat().st_size

            with EvaluationSessionLocal() as session:
                document_id = create_document(
                    session,
                    user_id=user_id,
                    chat_id=chat_id,
                    filename=fixture_path.name,
                    file_size=file_size,
                    page_count=len(pages),
                )

                session.commit()

            print(
                f"Document ID: {document_id}"
            )
            print(
                f"Extracted pages: {len(pages)}"
            )
            print(
                f"Embedding provider: {provider.value}"
            )

            result = await DocumentIngestionService.ingest(
                user_id=user_id,
                document_id=document_id,
                pages=pages,
                embedding_provider=provider,
            )

            DocumentRepository.update_status(
                document_id=document_id,
                user_id=user_id,
                status="ready",
            )

            with EvaluationSessionLocal() as session:
                rows = fetch_manifest_rows(
                    session,
                    user_id=user_id,
                    document_id=document_id,
                )

                validate_manifest_rows(
                    rows,
                    document_id=document_id,
                )

            print(
                f"Chunks indexed: {result['chunks_indexed']}"
            )

            if result["chunks_indexed"] != len(rows):
                raise RuntimeError(
                    f"Document {document_id}: ingestion reported "
                    f"{result['chunks_indexed']} chunks, but database "
                    f"contains {len(rows)} chunks."
                )

            document_entries.append(
                {
                    "document_key": fixture_path.stem,
                    "filename": fixture_path.name,
                    "user_id": user_id,
                    "chat_id": chat_id,
                    "document_id": document_id,
                    "page_count": len(pages),
                    "chunk_count": len(rows),
                    "chunks": rows,
                }
            )

        parsed_database_name = (
            urlparse(test_database_url)
            .path
            .lstrip("/")
            .split("?", 1)[0]
        )

        write_manifest(
            manifest_path,
            test_database_name=parsed_database_name,
            provider=provider.value,
            documents=document_entries,
        )

        total_chunks = sum(
            document["chunk_count"]
            for document in document_entries
        )

        print()
        print("=" * 72)
        print("P3-04 RETRIEVAL EVALUATION CORPUS SEEDED")
        print("=" * 72)
        print(
            f"User ID:       {user_id}"
        )
        print(
            f"Chat ID:       {chat_id}"
        )
        print(
            f"Documents:     {len(document_entries)}"
        )
        print(
            f"Total chunks:  {total_chunks}"
        )
        print(
            f"Provider:      {provider.value}"
        )
        print(
            f"Manifest:      {manifest_path}"
        )
        print("=" * 72)

    finally:
        if original_bind is not None:
            app_session_module.SessionLocal.configure(
                bind=original_bind
            )

        evaluation_engine.dispose()


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description=(
            "Seed the isolated P3-04 retrieval evaluation database."
        )
    )

    parser.add_argument(
        "--fixture-dir",
        type=Path,
        default=DEFAULT_FIXTURE_DIR,
        help=(
            "Directory containing the four generated retrieval PDFs."
        ),
    )

    parser.add_argument(
        "--manifest",
        type=Path,
        default=DEFAULT_MANIFEST,
        help=(
            "Output path for the generated chunk manifest."
        ),
    )

    return parser.parse_args()


def main() -> None:
    """CLI entry point."""
    args = parse_args()

    asyncio.run(
        seed(
            fixture_dir=args.fixture_dir,
            manifest_path=args.manifest,
        )
    )


if __name__ == "__main__":
    main()
