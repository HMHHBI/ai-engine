"""enforce_document_chunk_index_uniqueness

Revision ID: b39cf144f3a2
Revises: c7efc0cfd435
Create Date: 2026-09-11
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b39cf144f3a2'
down_revision: Union[str, None] = 'c7efc0cfd435'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Enforce nullable=False on chunk_index
    op.alter_column(
        "document_chunks",
        "chunk_index",
        existing_type=sa.Integer(),
        nullable=False,
    )
    # 2. Add UniqueConstraint on (document_id, chunk_index)
    op.create_unique_constraint(
        "uq_document_chunks_doc_chunk_idx",
        "document_chunks",
        ["document_id", "chunk_index"],
    )


def downgrade() -> None:
    # 1. Drop UniqueConstraint
    op.drop_constraint(
        "uq_document_chunks_doc_chunk_idx",
        "document_chunks",
        type_="unique",
    )
    # 2. Revert chunk_index back to nullable=True
    op.alter_column(
        "document_chunks",
        "chunk_index",
        existing_type=sa.Integer(),
        nullable=True,
    )
