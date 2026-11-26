"""create research run outbox

Revision ID: g4b2d3e5f7a8
Revises: f3a1c2d4e5f6
Create Date: 2026-11-25 18:45:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "g4b2d3e5f7a8"
down_revision: Union[str, Sequence[str], None] = "f3a1c2d4e5f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "research_run_outbox",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("research_run_id", sa.Integer(), nullable=False),
        sa.Column("workspace_id", sa.Integer(), nullable=False),
        sa.Column(
            "status",
            sa.String(length=20),
            server_default=sa.text("'pending'"),
            nullable=False,
        ),
        sa.Column(
            "payload",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "attempts",
            sa.Integer(),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status IN ('pending', 'published')",
            name="ck_research_run_outbox_valid_status",
        ),
        sa.ForeignKeyConstraint(
            ["research_run_id"],
            ["research_runs.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["workspaces.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_research_run_outbox_research_run_id",
        "research_run_outbox",
        ["research_run_id"],
        unique=False,
    )
    op.create_index(
        "ix_research_run_outbox_workspace_id",
        "research_run_outbox",
        ["workspace_id"],
        unique=False,
    )
    op.create_index(
        "ix_research_run_outbox_status",
        "research_run_outbox",
        ["status"],
        unique=False,
    )
    op.create_index(
        "ix_research_run_outbox_status_created",
        "research_run_outbox",
        ["status", "created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_research_run_outbox_status_created", table_name="research_run_outbox")
    op.drop_index("ix_research_run_outbox_status", table_name="research_run_outbox")
    op.drop_index("ix_research_run_outbox_workspace_id", table_name="research_run_outbox")
    op.drop_index("ix_research_run_outbox_research_run_id", table_name="research_run_outbox")
    op.drop_table("research_run_outbox")
