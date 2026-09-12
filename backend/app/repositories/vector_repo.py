from __future__ import annotations
import re

from typing import Any, Sequence

from sqlalchemy import delete, func, select, or_

from app.db.models import Chat, Document, DocumentChunk
from app.db.session import session_scope


class VectorRepository:
    """
    Tenant-scoped repository for document chunks and vector search.

    Ownership invariant:
        user_id
            -> Document.user_id
            -> Document.chat_id
            -> Chat.user_id
            -> DocumentChunk.document_id

    `document_id` is the source of truth for vector ownership.

    `chat_id` is intentionally populated on DocumentChunk for the current
    F3-A transition and remains a legacy compatibility field until the
    later cleanup phase removes it.
    """

    VALID_STATUSES = {"processing", "ready", "failed"}

    @staticmethod
    def _validate_ids(
        user_id: int,
        document_id: int,
    ) -> None:
        if user_id <= 0:
            raise ValueError("user_id must be a positive integer.")

        if document_id <= 0:
            raise ValueError("document_id must be a positive integer.")

    @staticmethod
    def _get_owned_document(
        db,
        *,
        user_id: int,
        document_id: int,
        lock: bool = False,
    ) -> Document | None:
        """
        Resolve a document only when BOTH ownership relationships are valid:

        1. Document.user_id == authenticated user
        2. Document.chat_id belongs to authenticated user

        This deliberately does not trust Document.user_id alone.
        """
        query = (
            select(Document)
            .join(
                Chat,
                Chat.id == Document.chat_id,
            )
            .where(
                Document.id == document_id,
                Document.user_id == user_id,
                Chat.user_id == user_id,
            )
        )

        if lock:
            query = query.with_for_update()

        return db.execute(query).scalar_one_or_none()

    @staticmethod
    def replace_document_chunks(
        user_id: int,
        document_id: int,
        chunks_with_embeddings: Sequence[tuple[Any, list[float]]],
        pdf_context: str | None = None,
    ) -> list[dict[str, Any]]:
        """
        Atomically replace all chunks belonging to one document.

        Ownership is verified through both:

            Document.user_id == user_id
            Chat.user_id == user_id

        The Document row is locked for the duration of the transaction,
        serializing concurrent replacements of the same document.

        Every new DocumentChunk receives:

            document_id = document.id
            chat_id     = document.chat_id

        `chat_id` is retained only as transitional compatibility.
        """
        VectorRepository._validate_ids(
            user_id=user_id,
            document_id=document_id,
        )

        if not chunks_with_embeddings:
            raise ValueError("chunks_with_embeddings cannot be empty.")

        with session_scope() as db:
            document = VectorRepository._get_owned_document(
                db,
                user_id=user_id,
                document_id=document_id,
                lock=True,
            )

            if document is None:
                raise LookupError("Document not found.")

            chat_id = document.chat_id

            # Delete ONLY this document's chunks.
            #
            # Never delete by chat_id here because one chat may contain
            # multiple documents after the F3-A migration.
            db.execute(
                delete(DocumentChunk).where(
                    DocumentChunk.document_id == document.id,
                )
            )

            db_objs: list[DocumentChunk] = []

            for chunk, embedding in chunks_with_embeddings:
                if not embedding:
                    continue

                db_obj = DocumentChunk(
                    document_id=document.id,
                    chat_id=chat_id,
                    content=chunk.text,
                    page_number=chunk.page_number,
                    chunk_index=chunk.chunk_index,
                    embedding=embedding,
                )

                db.add(db_obj)
                db_objs.append(db_obj)

            if not db_objs:
                raise ValueError(
                    "No valid document chunks with embeddings were provided."
                )

            # Transitional compatibility:
            # keep the legacy Chat.pdf_context populated until the later
            # F3 cleanup removes that field.
            chat = db.execute(
                select(Chat).where(
                    Chat.id == chat_id,
                    Chat.user_id == user_id,
                )
            ).scalar_one_or_none()

            if chat is None:
                raise LookupError("Chat not found.")

            if pdf_context is not None:
                chat = db.execute(
                    select(Chat).where(
                        Chat.id == chat_id,
                        Chat.user_id == user_id,
                    )
                ).scalar_one_or_none()

                if chat is None:
                    raise LookupError("Chat not found.")

                chat.pdf_context = pdf_context

            db.flush()

            return [
                {
                    "id": chunk.id,
                    "chat_id": chunk.chat_id,
                    "document_id": chunk.document_id,
                    "page_number": chunk.page_number,
                    "chunk_index": chunk.chunk_index,
                }
                for chunk in db_objs
            ]

    @staticmethod
    def store_document_chunks(
        user_id: int,
        document_id: int,
        chunks_with_embeddings: Sequence[tuple[Any, list[float]]],
    ) -> list[dict[str, Any]]:
        """
        Store chunks for one owned document.

        Every inserted chunk receives both:

            document_id = document.id
            chat_id     = document.chat_id

        Ownership requires BOTH:

            document.user_id == user_id
            document.chat.user_id == user_id
        """
        VectorRepository._validate_ids(
            user_id=user_id,
            document_id=document_id,
        )

        if not chunks_with_embeddings:
            return []

        with session_scope() as db:
            document = VectorRepository._get_owned_document(
                db,
                user_id=user_id,
                document_id=document_id,
            )

            if document is None:
                raise LookupError("Document not found.")

            chat_id = document.chat_id

            db_objs: list[DocumentChunk] = []

            for chunk, embedding in chunks_with_embeddings:
                if not embedding:
                    continue

                db_obj = DocumentChunk(
                    document_id=document.id,
                    chat_id=chat_id,
                    content=chunk.text,
                    page_number=chunk.page_number,
                    chunk_index=chunk.chunk_index,
                    embedding=embedding,
                )

                db.add(db_obj)
                db_objs.append(db_obj)

            if not db_objs:
                return []

            db.flush()

            return [
                {
                    "id": chunk.id,
                    "chat_id": chunk.chat_id,
                    "document_id": chunk.document_id,
                    "page_number": chunk.page_number,
                    "chunk_index": chunk.chunk_index,
                }
                for chunk in db_objs
            ]

    @staticmethod
    def search_similar_chunks(
        user_id: int,
        document_id: int,
        query_vector: list[float],
        top_k: int = 6,
        max_distance: float = 0.70,
        adaptive_margin: float = 0.15,
    ) -> list[dict[str, Any]]:
        """
        Search vectors belonging to exactly one owned document.

        The query is constrained by:

            DocumentChunk.document_id == document_id
            Document.user_id == user_id
            Chat.user_id == user_id

        Therefore a document ID from another tenant cannot expose vectors.
        """
        VectorRepository._validate_ids(
            user_id=user_id,
            document_id=document_id,
        )

        if not query_vector:
            return []

        if top_k <= 0 or top_k > 50:
            raise ValueError("top_k must be between 1 and 50.")

        if max_distance < 0 or adaptive_margin < 0:
            raise ValueError("Distance parameters cannot be negative.")

        distance = DocumentChunk.embedding.cosine_distance(query_vector).label(
            "distance"
        )

        with session_scope() as db:
            results = db.execute(
                select(DocumentChunk, distance)
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
                    DocumentChunk.embedding.is_not(None),
                )
                .order_by(distance)
                .limit(top_k)
            ).all()

            if not results:
                return []

            best_distance = float(results[0].distance)

            if best_distance > max_distance:
                return []

            adaptive_limit = min(
                best_distance + adaptive_margin,
                max_distance,
            )

            filtered_results = [
                row for row in results if float(row.distance) <= adaptive_limit
            ]

            return [
                {
                    "id": chunk.id,
                    "document_id": chunk.document_id,
                    "chat_id": chunk.chat_id,
                    "content": chunk.content,
                    "page_number": chunk.page_number,
                    "chunk_index": chunk.chunk_index,
                    "distance": float(distance_value),
                }
                for chunk, distance_value in filtered_results
            ]

    @staticmethod
    def _build_sparse_tsquery(query_text: str) -> str:
        """
        Build an OR-based tsquery string excluding common English question stopwords.
        """
        stopwords = {
            "a", "about", "above", "after", "again", "against", "all", "am", "an",
            "and", "any", "are", "aren't", "as", "at", "be", "because", "been",
            "before", "being", "below", "between", "both", "but", "by", "can",
            "cannot", "could", "couldn't", "did", "didn't", "do", "does", "doesn't",
            "doing", "don't", "down", "during", "each", "few", "for", "from",
            "further", "had", "hadn't", "has", "hasn't", "have", "haven't", "having",
            "he", "her", "here", "hers", "herself", "him", "himself", "his", "how",
            "i", "if", "in", "into", "is", "isn't", "it", "its", "itself", "let's",
            "me", "more", "most", "mustn't", "my", "myself", "no", "nor", "not",
            "of", "off", "on", "once", "only", "or", "other", "ought", "our", "ours",
            "ourselves", "out", "over", "own", "same", "shan't", "she", "should",
            "shouldn't", "so", "some", "such", "than", "that", "the", "their",
            "theirs", "them", "themselves", "then", "there", "these", "they", "this",
            "those", "through", "to", "too", "under", "until", "up", "very", "was",
            "wasn't", "we", "were", "weren't", "what", "when", "where", "which",
            "while", "who", "whom", "why", "with", "won't", "would", "wouldn't",
            "you", "your", "yours", "yourself", "yourselves"
        }
        tokens = re.findall(r"[a-zA-Z0-9_\-\.]{2,}", query_text)
        cleaned = [re.sub(r"[^a-zA-Z0-9]", "", t) for t in tokens]
        meaningful = [t for t in cleaned if len(t) >= 2 and t.lower() not in stopwords]
        
        # Fallback to all cleaned tokens if all were stopwords
        tokens_to_use = meaningful if meaningful else [t for t in cleaned if len(t) >= 2]
        if not tokens_to_use:
            return ""
        return " | ".join(tokens_to_use)

    @staticmethod
    def search_sparse_chunks(
        user_id: int,
        document_id: int,
        query_text: str,
        top_k: int = 20,
    ) -> list[dict[str, Any]]:
        """
        Full-Text Search (Sparse Lexical) scoped strictly to owned document.
        Uses OR-based tsquery with ts_rank_cd normalized by document length.
        """
        VectorRepository._validate_ids(user_id=user_id, document_id=document_id)
        cleaned_text = (query_text or "").strip()
        if not cleaned_text:
            return []

        ts_query_str = VectorRepository._build_sparse_tsquery(cleaned_text)
        if not ts_query_str:
            return []

        ts_vector = func.to_tsvector("english", DocumentChunk.content)
        ts_query = func.to_tsquery("english", ts_query_str)
        # 32 = rank divided by (length + 1)
        rank_expr = func.ts_rank_cd(ts_vector, ts_query, 32).label("sparse_score")

        with session_scope() as db:
            results = db.execute(
                select(DocumentChunk, rank_expr)
                .join(Document, Document.id == DocumentChunk.document_id)
                .join(Chat, Chat.id == Document.chat_id)
                .where(
                    DocumentChunk.document_id == document_id,
                    Document.user_id == user_id,
                    Chat.user_id == user_id,
                    ts_vector.op("@@")(ts_query),
                )
                .order_by(rank_expr.desc())
                .limit(top_k)
            ).all()

            return [
                {
                    "id": chunk.id,
                    "document_id": chunk.document_id,
                    "chat_id": chunk.chat_id,
                    "content": chunk.content,
                    "page_number": chunk.page_number,
                    "chunk_index": chunk.chunk_index,
                    "score": float(sparse_score),
                }
                for chunk, sparse_score in results
            ]

    @staticmethod
    def search_hybrid_chunks(
        user_id: int,
        document_id: int,
        query_text: str,
        query_vector: list[float],
        top_k: int = 6,
        candidate_k: int = 20,
        rrf_k: int = 60,
        dense_weight: float = 1.0,
        sparse_weight: float = 1.0,
        max_distance: float = 0.70,
        adaptive_margin: float = 0.15,
    ) -> list[dict[str, Any]]:
        """
        Hybrid retrieval combining Dense Vector Search (pgvector) and Sparse
        Full-Text Search via Reciprocal Rank Fusion (RRF).
        """
        VectorRepository._validate_ids(user_id=user_id, document_id=document_id)

        # 1. Fetch dense candidates
        dense_candidates = VectorRepository.search_similar_chunks(
            user_id=user_id,
            document_id=document_id,
            query_vector=query_vector,
            top_k=max(top_k, candidate_k),
            max_distance=max_distance,
            adaptive_margin=adaptive_margin,
        )

        # 2. Fetch sparse lexical candidates
        sparse_candidates = VectorRepository.search_sparse_chunks(
            user_id=user_id,
            document_id=document_id,
            query_text=query_text,
            top_k=max(top_k, candidate_k),
        )

        # 3. Reciprocal Rank Fusion (RRF)
        rrf_scores: dict[int, float] = {}
        chunk_map: dict[int, dict[str, Any]] = {}

        for rank, item in enumerate(dense_candidates, start=1):
            cid = item["id"]
            rrf_scores[cid] = rrf_scores.get(cid, 0.0) + (dense_weight / (rrf_k + rank))
            chunk_map[cid] = item

        for rank, item in enumerate(sparse_candidates, start=1):
            cid = item["id"]
            rrf_scores[cid] = rrf_scores.get(cid, 0.0) + (sparse_weight / (rrf_k + rank))
            if cid not in chunk_map:
                chunk_map[cid] = item

        # 4. Sort by combined RRF score descending
        sorted_chunk_ids = sorted(
            rrf_scores.keys(),
            key=lambda cid: rrf_scores[cid],
            reverse=True,
        )

        final_chunks: list[dict[str, Any]] = []
        for cid in sorted_chunk_ids[:top_k]:
            data = dict(chunk_map[cid])
            data["rrf_score"] = float(rrf_scores[cid])
            final_chunks.append(data)

        return final_chunks

    @staticmethod
    def delete_document_chunks(
        user_id: int,
        document_id: int,
    ) -> bool:
        """
        Delete all chunks belonging to one owned document.

        Deletion is document-scoped, never chat-scoped.
        """
        VectorRepository._validate_ids(
            user_id=user_id,
            document_id=document_id,
        )

        with session_scope() as db:
            document = VectorRepository._get_owned_document(
                db,
                user_id=user_id,
                document_id=document_id,
            )

            if document is None:
                return False

            db.execute(
                delete(DocumentChunk).where(
                    DocumentChunk.document_id == document.id,
                )
            )

            return True
