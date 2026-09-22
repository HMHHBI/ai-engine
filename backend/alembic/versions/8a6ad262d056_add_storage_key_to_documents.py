"""add storage_key to documents

Revision ID: 8a6ad262d056
Revises: b39cf144f3a2
Create Date: 2026-09-18 10:11:08.113272

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "8a6ad262d056"
down_revision: Union[str, Sequence[str], None] = "b39cf144f3a2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("documents", sa.Column("storage_key", sa.Text(), nullable=True))
    op.create_index(
        op.f("ix_documents_storage_key"), "documents", ["storage_key"], unique=True
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_documents_storage_key"), table_name="documents")
    op.drop_column("documents", "storage_key")
