"""create audit_events table

Revision ID: 832700766b8f
Revises: 40b9349881f2
Create Date: 2026-10-11 12:12:13.013946

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '832700766b8f'
down_revision: Union[str, Sequence[str], None] = '40b9349881f2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'audit_events',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('actor_id', sa.Integer(), nullable=True),
        sa.Column('workspace_id', sa.Integer(), nullable=True),
        sa.Column('action', sa.String(length=80), nullable=False),
        sa.Column('resource_type', sa.String(length=60), nullable=False),
        sa.Column('resource_id', sa.String(length=60), nullable=True),
        sa.Column('outcome', sa.String(length=20), nullable=False),
        sa.Column('metadata_payload', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column('ip_address', sa.String(length=45), nullable=True),
        sa.Column('user_agent', sa.String(length=255), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['actor_id'], ['users.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['workspace_id'], ['workspaces.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_audit_events_action'), 'audit_events', ['action'], unique=False)
    op.create_index('ix_audit_events_action_created', 'audit_events', ['action', 'created_at'], unique=False)
    op.create_index(op.f('ix_audit_events_actor_id'), 'audit_events', ['actor_id'], unique=False)
    op.create_index(op.f('ix_audit_events_created_at'), 'audit_events', ['created_at'], unique=False)
    op.create_index('ix_audit_events_workspace_created', 'audit_events', ['workspace_id', 'created_at'], unique=False)
    op.create_index(op.f('ix_audit_events_workspace_id'), 'audit_events', ['workspace_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_audit_events_workspace_id'), table_name='audit_events')
    op.drop_index('ix_audit_events_workspace_created', table_name='audit_events')
    op.drop_index(op.f('ix_audit_events_created_at'), table_name='audit_events')
    op.drop_index(op.f('ix_audit_events_actor_id'), table_name='audit_events')
    op.drop_index('ix_audit_events_action_created', table_name='audit_events')
    op.drop_index(op.f('ix_audit_events_action'), table_name='audit_events')
    op.drop_table('audit_events')
