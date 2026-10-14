"""add_hnsw_vector_index_to_document_chunks

Revision ID: d8f2f05bbd84
Revises: 832700766b8f
Create Date: 2026-10-14 16:36:58.978601

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd8f2f05bbd84'
down_revision: Union[str, Sequence[str], None] = '832700766b8f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema: Create HNSW vector cosine index on document_chunks."""
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_document_chunks_embedding_hnsw
        ON document_chunks
        USING hnsw (embedding vector_cosine_ops)
        WITH (m = 16, ef_construction = 64);
        """
    )


def downgrade() -> None:
    """Downgrade schema: Drop HNSW vector cosine index."""
    op.execute(
        """
        DROP INDEX IF EXISTS ix_document_chunks_embedding_hnsw;
        """
    )
