"""add_chat_persona_and_custom_instructions

Revision ID: e1256d638e34
Revises: 21f288e57a41
Create Date: 2026-09-04 18:02:15.070220

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "e1256d638e34"
down_revision: Union[str, Sequence[str], None] = "21f288e57a41"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "chats",
        sa.Column(
            "persona", sa.String(length=50), nullable=False, server_default="default"
        ),
    )
    op.add_column(
        "chats",
        sa.Column("custom_instructions", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("chats", "custom_instructions")
    op.drop_column("chats", "persona")
