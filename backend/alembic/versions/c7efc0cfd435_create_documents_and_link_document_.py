"""create documents and link document chunks

Revision ID: c7efc0cfd435
Revises: e1256d638e34
Create Date: 2026-09-06 17:30:47.111062

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "c7efc0cfd435"
down_revision: Union[str, Sequence[str], None] = "e1256d638e34"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""

    # ----------------------------------------------------------
    # 1. Create documents table
    # ----------------------------------------------------------

    op.create_table(
        "documents",
        sa.Column(
            "id",
            sa.Integer(),
            nullable=False,
        ),
        sa.Column(
            "user_id",
            sa.Integer(),
            nullable=False,
        ),
        sa.Column(
            "chat_id",
            sa.Integer(),
            nullable=False,
        ),
        sa.Column(
            "filename",
            sa.String(length=255),
            nullable=False,
        ),
        sa.Column(
            "mime_type",
            sa.String(length=100),
            nullable=False,
        ),
        sa.Column(
            "file_size",
            sa.BigInteger(),
            nullable=True,
        ),
        sa.Column(
            "page_count",
            sa.Integer(),
            nullable=True,
        ),
        sa.Column(
            "storage_url",
            sa.Text(),
            nullable=True,
        ),
        sa.Column(
            "status",
            sa.String(length=20),
            nullable=False,
            server_default="processing",
        ),
        sa.Column(
            "error_message",
            sa.Text(),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(
            ["chat_id"],
            ["chats.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_index(
        "ix_documents_id",
        "documents",
        ["id"],
        unique=False,
    )

    op.create_index(
        "ix_documents_user_id",
        "documents",
        ["user_id"],
        unique=False,
    )

    op.create_index(
        "ix_documents_chat_id",
        "documents",
        ["chat_id"],
        unique=False,
    )

    op.create_index(
        "ix_documents_chat_id_id",
        "documents",
        ["chat_id", "id"],
        unique=False,
    )

    # ----------------------------------------------------------
    # 2. Add document_id as nullable transitional column
    # ----------------------------------------------------------

    op.add_column(
        "document_chunks",
        sa.Column(
            "document_id",
            sa.Integer(),
            nullable=True,
        ),
    )

    op.create_index(
        "ix_document_chunks_document_id",
        "document_chunks",
        ["document_id"],
        unique=False,
    )

    # ----------------------------------------------------------
    # 3. Backfill one Document per existing chat document state
    # ----------------------------------------------------------

    op.execute(sa.text("""
            INSERT INTO documents (
                user_id,
                chat_id,
                filename,
                mime_type,
                file_size,
                page_count,
                storage_url,
                status,
                error_message,
                created_at,
                updated_at
            )
            SELECT
                c.user_id,
                c.id,
                'legacy-chat-' || c.id || '.pdf',
                'application/pdf',
                NULL,
                (
                    SELECT MAX(dc.page_number)
                    FROM document_chunks dc
                    WHERE dc.chat_id = c.id
                      AND dc.page_number IS NOT NULL
                ),
                NULL,
                'ready',
                NULL,
                now(),
                now()
            FROM chats c
            WHERE c.pdf_context IS NOT NULL
               OR EXISTS (
                    SELECT 1
                    FROM document_chunks dc
                    WHERE dc.chat_id = c.id
               )
            """))

    # ----------------------------------------------------------
    # 4. Link existing chunks to their migrated Document
    # ----------------------------------------------------------

    op.execute(sa.text("""
            UPDATE document_chunks dc
            SET document_id = d.id
            FROM documents d
            WHERE d.chat_id = dc.chat_id
            """))

    # ----------------------------------------------------------
    # 5. Migration invariants
    # ----------------------------------------------------------

    op.execute(sa.text("""
            DO $$
            DECLARE
                null_chunk_count BIGINT;
                invalid_document_count BIGINT;
                invalid_chunk_count BIGINT;
                legacy_chat_count BIGINT;
                migrated_chat_count BIGINT;
                chunk_count BIGINT;
                linked_chunk_count BIGINT;
            BEGIN
                -- Every existing chunk must now have a document.
                SELECT COUNT(*)
                INTO null_chunk_count
                FROM document_chunks
                WHERE document_id IS NULL;

                IF null_chunk_count <> 0 THEN
                    RAISE EXCEPTION
                        'F3-A invariant failed: % document chunks have NULL document_id',
                        null_chunk_count;
                END IF;

                -- Every migrated document must belong to an existing chat.
                SELECT COUNT(*)
                INTO invalid_document_count
                FROM documents d
                LEFT JOIN chats c
                    ON c.id = d.chat_id
                WHERE c.id IS NULL;

                IF invalid_document_count <> 0 THEN
                    RAISE EXCEPTION
                        'F3-A invariant failed: % documents reference missing chats',
                        invalid_document_count;
                END IF;

                -- Document ownership must match chat ownership.
                SELECT COUNT(*)
                INTO invalid_chunk_count
                FROM documents d
                JOIN chats c
                    ON c.id = d.chat_id
                WHERE d.user_id <> c.user_id;

                IF invalid_chunk_count <> 0 THEN
                    RAISE EXCEPTION
                        'F3-A invariant failed: % documents have incorrect user ownership',
                        invalid_chunk_count;
                END IF;

                -- Every chunk must point to a document belonging to
                -- the same chat as the legacy chat_id.
                SELECT COUNT(*)
                INTO invalid_chunk_count
                FROM document_chunks dc
                JOIN documents d
                    ON d.id = dc.document_id
                WHERE dc.chat_id <> d.chat_id;

                IF invalid_chunk_count <> 0 THEN
                    RAISE EXCEPTION
                        'F3-A invariant failed: % chunks have mismatched chat/document ownership',
                        invalid_chunk_count;
                END IF;

                -- Every chunk must point to a document belonging to
                -- the same user as its chat.
                SELECT COUNT(*)
                INTO invalid_chunk_count
                FROM document_chunks dc
                JOIN documents d
                    ON d.id = dc.document_id
                JOIN chats c
                    ON c.id = dc.chat_id
                WHERE d.user_id <> c.user_id;

                IF invalid_chunk_count <> 0 THEN
                    RAISE EXCEPTION
                        'F3-A invariant failed: % chunks have mismatched user ownership',
                        invalid_chunk_count;
                END IF;

                -- Every legacy chat with document state must have
                -- exactly one migrated document.
                SELECT COUNT(*)
                INTO legacy_chat_count
                FROM chats c
                WHERE c.pdf_context IS NOT NULL
                   OR EXISTS (
                        SELECT 1
                        FROM document_chunks dc
                        WHERE dc.chat_id = c.id
                   );

                SELECT COUNT(*)
                INTO migrated_chat_count
                FROM (
                    SELECT d.chat_id
                    FROM documents d
                    GROUP BY d.chat_id
                ) migrated;

                IF legacy_chat_count <> migrated_chat_count THEN
                    RAISE EXCEPTION
                        'F3-A invariant failed: legacy chats (%) != migrated chats (%)',
                        legacy_chat_count,
                        migrated_chat_count;
                END IF;

                -- No chunk may disappear or multiply during linkage.
                SELECT COUNT(*)
                INTO chunk_count
                FROM document_chunks;

                SELECT COUNT(*)
                INTO linked_chunk_count
                FROM document_chunks
                WHERE document_id IS NOT NULL;

                IF chunk_count <> linked_chunk_count THEN
                    RAISE EXCEPTION
                        'F3-A invariant failed: total chunks (%) != linked chunks (%)',
                        chunk_count,
                        linked_chunk_count;
                END IF;

                -- Every migrated document must have the expected
                -- ready state.
                SELECT COUNT(*)
                INTO invalid_document_count
                FROM documents
                WHERE status <> 'ready';

                IF invalid_document_count <> 0 THEN
                    RAISE EXCEPTION
                        'F3-A invariant failed: % migrated documents are not ready',
                        invalid_document_count;
                END IF;
            END
            $$;
            """))

    # ----------------------------------------------------------
    # 6. document_id is now safe to make NOT NULL
    # ----------------------------------------------------------

    op.alter_column(
        "document_chunks",
        "document_id",
        existing_type=sa.Integer(),
        nullable=False,
    )

    # ----------------------------------------------------------
    # 7. Add the foreign key only after successful backfill
    # ----------------------------------------------------------

    op.create_foreign_key(
        "fk_document_chunks_document_id_documents",
        "document_chunks",
        "documents",
        ["document_id"],
        ["id"],
        ondelete="CASCADE",
    )

    # ----------------------------------------------------------
    # 8. Add composite index for document-scoped retrieval
    # ----------------------------------------------------------

    op.create_index(
        "ix_document_chunks_document_id_id",
        "document_chunks",
        ["document_id", "id"],
        unique=False,
    )


def downgrade() -> None:
    """Downgrade schema."""

    # ----------------------------------------------------------
    # 1. Remove the document foreign key/indexes
    # ----------------------------------------------------------

    op.drop_index(
        "ix_document_chunks_document_id_id",
        table_name="document_chunks",
    )

    op.drop_constraint(
        "fk_document_chunks_document_id_documents",
        "document_chunks",
        type_="foreignkey",
    )

    op.drop_index(
        "ix_document_chunks_document_id",
        table_name="document_chunks",
    )

    # ----------------------------------------------------------
    # 2. Remove transitional document_id
    # ----------------------------------------------------------

    op.drop_column(
        "document_chunks",
        "document_id",
    )

    # ----------------------------------------------------------
    # 3. Remove documents table
    # ----------------------------------------------------------

    op.drop_index(
        "ix_documents_chat_id_id",
        table_name="documents",
    )

    op.drop_index(
        "ix_documents_chat_id",
        table_name="documents",
    )

    op.drop_index(
        "ix_documents_user_id",
        table_name="documents",
    )

    op.drop_index(
        "ix_documents_id",
        table_name="documents",
    )

    op.drop_table("documents")
