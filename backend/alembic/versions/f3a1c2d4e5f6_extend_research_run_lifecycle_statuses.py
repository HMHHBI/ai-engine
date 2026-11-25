"""extend research run lifecycle statuses

Revision ID: f3a1c2d4e5f6
Revises: d8f2f05bbd84
Create Date: 2026-11-25 17:30:00.000000

"""
from typing import Sequence, Union

from alembic import op

revision: str = "f3a1c2d4e5f6"
down_revision: Union[str, Sequence[str], None] = "d8f2f05bbd84"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

NEW_STATUS_CHECK = (
    "status IN ('queued', 'running', 'retrieving', 'synthesizing', "
    "'validating', 'completed', 'failed', 'cancelled')"
)
OLD_STATUS_CHECK = "status IN ('queued', 'running', 'completed', 'failed')"


def upgrade() -> None:
    op.drop_constraint(
        "ck_research_runs_valid_status",
        "research_runs",
        type_="check",
    )
    op.create_check_constraint(
        "ck_research_runs_valid_status",
        "research_runs",
        NEW_STATUS_CHECK,
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_research_runs_valid_status",
        "research_runs",
        type_="check",
    )
    op.create_check_constraint(
        "ck_research_runs_valid_status",
        "research_runs",
        OLD_STATUS_CHECK,
    )
