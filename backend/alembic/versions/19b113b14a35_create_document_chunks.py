"""create document chunks

Revision ID: 19b113b14a35
Revises: 744e13609578
Create Date: 2026-08-22 20:44:34.729717

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from pgvector.sqlalchemy import Vector

# revision identifiers, used by Alembic.
revision: str = "19b113b14a35"
down_revision: Union[str, Sequence[str], None] = "744e13609578"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    op.create_table(
        "document_chunks",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("chat_id", sa.Integer(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("embedding", Vector(768), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(
            ["chat_id"],
            ["chats.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_index(
        "ix_document_chunks_id",
        "document_chunks",
        ["id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_document_chunks_id",
        table_name="document_chunks",
    )
    op.drop_table("document_chunks")
