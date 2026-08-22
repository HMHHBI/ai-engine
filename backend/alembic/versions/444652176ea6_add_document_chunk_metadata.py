"""add document chunk metadata

Revision ID: 444652176ea6
Revises: 19b113b14a35
Create Date: 2026-08-20 15:08:14.227390
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "444652176ea6"
down_revision: Union[str, Sequence[str], None] = "19b113b14a35"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "document_chunks",
        sa.Column("page_number", sa.Integer(), nullable=True),
    )
    op.add_column(
        "document_chunks",
        sa.Column("chunk_index", sa.Integer(), nullable=True),
    )
    op.create_index(
        op.f("ix_document_chunks_page_number"),
        "document_chunks",
        ["page_number"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_document_chunks_page_number"),
        table_name="document_chunks",
    )
    op.drop_column("document_chunks", "chunk_index")
    op.drop_column("document_chunks", "page_number")
