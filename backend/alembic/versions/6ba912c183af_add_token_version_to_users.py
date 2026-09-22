"""add_token_version_to_users

Revision ID: 6ba912c183af
Revises: 8a6ad262d056
Create Date: 2026-09-22 17:25:29.976223

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '6ba912c183af'
down_revision: Union[str, Sequence[str], None] = '8a6ad262d056'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'users',
        sa.Column('token_version', sa.Integer(), nullable=False, server_default='1')
    )


def downgrade() -> None:
    op.drop_column('users', 'token_version')
