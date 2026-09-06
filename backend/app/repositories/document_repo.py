from __future__ import annotations

from typing import Optional

from sqlalchemy import delete, select

from app.db.models import Chat, Document
from app.db.session import session_scope


class DocumentRepository:
    """
    Database repository for documents.

    Repository methods own their database sessions. Ownership-aware
    methods always verify the authenticated user through the owning
    chat and document relationship.
    """

    VALID_STATUSES = {
        "processing",
        "ready",
        "failed",
    }

    @staticmethod
    def _validate_ids(
        user_id: int,
        chat_id: Optional[int] = None,
        document_id: Optional[int] = None,
    ) -> None:
        if user_id <= 0:
            raise ValueError("user_id must be a positive integer.")

        if chat_id is not None and chat_id <= 0:
            raise ValueError("chat_id must be a positive integer.")

        if document_id is not None and document_id <= 0:
            raise ValueError("document_id must be a positive integer.")

    @staticmethod
    def _validate_document_fields(
        filename: str,
        mime_type: str,
        file_size: Optional[int],
        page_count: Optional[int],
    ) -> tuple[str, str]:
        normalized_filename = filename.strip()
        normalized_mime_type = mime_type.strip()

        if not normalized_filename:
            raise ValueError("filename cannot be empty.")

        if len(normalized_filename) > 255:
            raise ValueError("filename cannot exceed 255 characters.")

        if not normalized_mime_type:
            raise ValueError("mime_type cannot be empty.")

        if len(normalized_mime_type) > 100:
            raise ValueError("mime_type cannot exceed 100 characters.")

        if file_size is not None and file_size < 0:
            raise ValueError("file_size cannot be negative.")

        if page_count is not None and page_count < 0:
            raise ValueError("page_count cannot be negative.")

        return normalized_filename, normalized_mime_type

    @classmethod
    def _validate_status(cls, status: str) -> str:
        normalized_status = status.strip().lower()

        if normalized_status not in cls.VALID_STATUSES:
            raise ValueError(
                "Invalid document status. "
                "Expected 'processing', 'ready', or 'failed'."
            )

        return normalized_status

    @staticmethod
    def create(
        user_id: int,
        chat_id: int,
        filename: str,
        mime_type: str,
        file_size: Optional[int] = None,
        page_count: Optional[int] = None,
        storage_url: Optional[str] = None,
    ) -> Optional[Document]:
        """
        Create a processing document owned by the authenticated user.

        The chat ownership check is performed before the document is
        inserted.
        """
        DocumentRepository._validate_ids(
            user_id=user_id,
            chat_id=chat_id,
        )

        normalized_filename, normalized_mime_type = (
            DocumentRepository._validate_document_fields(
                filename=filename,
                mime_type=mime_type,
                file_size=file_size,
                page_count=page_count,
            )
        )

        normalized_storage_url = (
            storage_url.strip() if storage_url and storage_url.strip() else None
        )

        with session_scope() as db:
            chat_exists = db.execute(
                select(Chat.id).where(
                    Chat.id == chat_id,
                    Chat.user_id == user_id,
                )
            ).scalar_one_or_none()

            if chat_exists is None:
                return None

            document = Document(
                user_id=user_id,
                chat_id=chat_id,
                filename=normalized_filename,
                mime_type=normalized_mime_type,
                file_size=file_size,
                page_count=page_count,
                storage_url=normalized_storage_url,
                status="processing",
                error_message=None,
            )

            db.add(document)
            db.flush()

            return document

    @staticmethod
    def get_by_id(
        document_id: int,
    ) -> Optional[Document]:
        """
        Retrieve a document by primary key without applying user ownership.

        This method is intended for trusted internal workflows. User-facing
        operations must use get_owned_document().
        """
        if document_id <= 0:
            raise ValueError("document_id must be a positive integer.")

        with session_scope() as db:
            return db.execute(
                select(Document).where(
                    Document.id == document_id,
                )
            ).scalar_one_or_none()

    @staticmethod
    def get_owned_document(
        document_id: int,
        user_id: int,
    ) -> Optional[Document]:
        """
        Retrieve a document only when it belongs to the authenticated user.
        """
        DocumentRepository._validate_ids(
            user_id=user_id,
            document_id=document_id,
        )

        with session_scope() as db:
            return db.execute(
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
            ).scalar_one_or_none()

    @staticmethod
    def list_for_chat(
        chat_id: int,
        user_id: int,
    ) -> list[Document]:
        """
        List all documents belonging to a chat owned by the authenticated user.
        """
        DocumentRepository._validate_ids(
            user_id=user_id,
            chat_id=chat_id,
        )

        with session_scope() as db:
            chat_exists = db.execute(
                select(Chat.id).where(
                    Chat.id == chat_id,
                    Chat.user_id == user_id,
                )
            ).scalar_one_or_none()

            if chat_exists is None:
                return []

            return list(
                db.execute(
                    select(Document)
                    .where(
                        Document.chat_id == chat_id,
                        Document.user_id == user_id,
                    )
                    .order_by(Document.id.desc())
                ).scalars()
            )

    @staticmethod
    def update_status(
        document_id: int,
        user_id: int,
        status: str,
        error_message: Optional[str] = None,
    ) -> Optional[Document]:
        """
        Update document processing status with ownership verification.

        A non-empty error message is persisted only for failed documents.
        Successful documents clear any previous error message.
        """
        DocumentRepository._validate_ids(
            user_id=user_id,
            document_id=document_id,
        )

        normalized_status = DocumentRepository._validate_status(status)

        normalized_error_message = (
            error_message.strip() if error_message and error_message.strip() else None
        )

        if normalized_status != "failed":
            normalized_error_message = None

        with session_scope() as db:
            document = db.execute(
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
            ).scalar_one_or_none()

            if document is None:
                return None

            document.status = normalized_status
            document.error_message = normalized_error_message

            db.flush()

            return document

    @staticmethod
    def update_metadata(
        document_id: int,
        user_id: int,
        filename: Optional[str] = None,
        mime_type: Optional[str] = None,
        file_size: Optional[int] = None,
        page_count: Optional[int] = None,
        storage_url: Optional[str] = None,
    ) -> Optional[Document]:
        """
        Update document metadata with ownership verification.

        Only explicitly supplied fields are modified.
        """
        DocumentRepository._validate_ids(
            user_id=user_id,
            document_id=document_id,
        )

        normalized_filename: Optional[str] = None
        normalized_mime_type: Optional[str] = None

        if filename is not None:
            normalized_filename = filename.strip()

            if not normalized_filename:
                raise ValueError("filename cannot be empty.")

            if len(normalized_filename) > 255:
                raise ValueError("filename cannot exceed 255 characters.")

        if mime_type is not None:
            normalized_mime_type = mime_type.strip()

            if not normalized_mime_type:
                raise ValueError("mime_type cannot be empty.")

            if len(normalized_mime_type) > 100:
                raise ValueError("mime_type cannot exceed 100 characters.")

        if file_size is not None and file_size < 0:
            raise ValueError("file_size cannot be negative.")

        if page_count is not None and page_count < 0:
            raise ValueError("page_count cannot be negative.")

        normalized_storage_url: Optional[str] = None

        if storage_url is not None:
            normalized_storage_url = (
                storage_url.strip() if storage_url.strip() else None
            )

        with session_scope() as db:
            document = db.execute(
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
            ).scalar_one_or_none()

            if document is None:
                return None

            if filename is not None:
                document.filename = normalized_filename

            if mime_type is not None:
                document.mime_type = normalized_mime_type

            if file_size is not None:
                document.file_size = file_size

            if page_count is not None:
                document.page_count = page_count

            if storage_url is not None:
                document.storage_url = normalized_storage_url

            db.flush()

            return document

    @staticmethod
    def delete(
        document_id: int,
        user_id: int,
    ) -> bool:
        """
        Delete a document owned by the authenticated user.

        DocumentChunk rows are removed by the database ON DELETE CASCADE
        constraint on document_chunks.document_id.
        """
        DocumentRepository._validate_ids(
            user_id=user_id,
            document_id=document_id,
        )

        with session_scope() as db:
            document = db.execute(
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
            ).scalar_one_or_none()

            if document is None:
                return False

            db.delete(document)

            return True

    @staticmethod
    def get_active_for_chat(
        chat_id: int,
        user_id: int,
    ) -> Optional[Document]:
        """
        Retrieve the latest ready document for a chat owned by the user.

        Requires dual ownership:
            Chat.id == chat_id AND Chat.user_id == user_id
            Document.chat_id == chat_id AND Document.user_id == user_id
            Document.status == 'ready'

        Ordered deterministically by created_at DESC, id DESC.
        """
        DocumentRepository._validate_ids(
            user_id=user_id,
            chat_id=chat_id,
        )

        with session_scope() as db:
            return db.execute(
                select(Document)
                .join(
                    Chat,
                    Chat.id == Document.chat_id,
                )
                .where(
                    Document.chat_id == chat_id,
                    Document.user_id == user_id,
                    Chat.id == chat_id,
                    Chat.user_id == user_id,
                    Document.status == "ready",
                )
                .order_by(
                    Document.created_at.desc(),
                    Document.id.desc(),
                )
                .limit(1)
            ).scalar_one_or_none()
