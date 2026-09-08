import argparse
import math
import random
from typing import Tuple

from app.db.session import SessionLocal
from app.db.models import User, Chat, Document, DocumentChunk
from app.repositories.user_repo import UserRepository


def generate_synthetic_unit_vector(dim: int = 768) -> list[float]:
    vec = [random.gauss(0, 1) for _ in range(dim)]
    norm = math.sqrt(sum(x * x for x in vec)) or 1.0
    return [round(x / norm, 6) for x in vec]


def seed_rag_document(target_chunks: int, email: str = "perf_test_runner@benchmark.internal") -> Tuple[int, int]:
    db = SessionLocal()
    try:
        user = UserRepository.get_by_email(db, email=email)
        if not user:
            raise RuntimeError(f"Benchmark user '{email}' not found. Run health/auth benchmark once to create user.")

        chat = Chat(
            user_id=user.id,
            title=f"Benchmark RAG Session ({target_chunks} chunks)",
            pdf_context=f"Indexed File: benchmark_doc_{target_chunks}.pdf",
        )
        db.add(chat)
        db.commit()
        db.refresh(chat)

        doc = Document(
            user_id=user.id,
            chat_id=chat.id,
            filename=f"benchmark_doc_{target_chunks}.pdf",
            mime_type="application/pdf",
            file_size=target_chunks * 500,
            page_count=max(1, target_chunks // 5),
            status="ready",
        )
        db.add(doc)
        db.commit()
        db.refresh(doc)

        print(f"Generating and bulk inserting {target_chunks} chunks (dim=768)...")
        base_vector = generate_synthetic_unit_vector(768)
        chunks_to_insert = []

        batch_size = 500
        for i in range(target_chunks):
            # Introduce slight variation around base vector
            vec = [(val + random.uniform(-0.02, 0.02)) for val in base_vector]
            norm = math.sqrt(sum(x * x for x in vec)) or 1.0
            unit_vec = [round(x / norm, 6) for x in vec]

            chunk = DocumentChunk(
                chat_id=chat.id,
                document_id=doc.id,
                content=f"Benchmark synthetic chunk {i} discussing distributed systems, async IO, and vector search scalability.",
                page_number=(i // 5) + 1,
                chunk_index=i,
                embedding=unit_vec,
            )
            chunks_to_insert.append(chunk)

            if len(chunks_to_insert) >= batch_size:
                db.bulk_save_objects(chunks_to_insert)
                db.commit()
                chunks_to_insert.clear()

        if chunks_to_insert:
            db.bulk_save_objects(chunks_to_insert)
            db.commit()

        print(f"Seeded document_id={doc.id} with {target_chunks} chunks in chat_id={chat.id}")
        return chat.id, doc.id
    finally:
        db.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Seed RAG Benchmark Chunks")
    parser.add_argument("--chunks", type=int, default=50, choices=[50, 500, 5000], help="Number of chunks")
    args = parser.parse_args()
    seed_rag_document(args.chunks)
