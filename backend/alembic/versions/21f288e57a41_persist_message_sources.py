"""persist message sources

Revision ID: 21f288e57a41
Revises: 7a99b1a5acae
Create Date: 2026-09-04 16:27:07.173719

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

# revision identifiers, used by Alembic.
revision: str = "21f288e57a41"
down_revision: Union[str, Sequence[str], None] = "7a99b1a5acae"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "messages",
        sa.Column(
            "sources",
            JSONB(),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column(
        "messages",
        "sources",
    )
