"""create research runs and document provenance

Revision ID: 40b9349881f2
Revises: 8408ff62ae6d
Create Date: 2026-10-11 11:41:50.018944

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '40b9349881f2'
down_revision: Union[str, Sequence[str], None] = '8408ff62ae6d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'research_runs',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('workspace_id', sa.Integer(), nullable=False),
        sa.Column('requester_id', sa.Integer(), nullable=False),
        sa.Column('query', sa.Text(), nullable=False),
        sa.Column('status', sa.String(length=20), server_default='queued', nullable=False),
        sa.Column('answer', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('run_metadata', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("status IN ('queued', 'running', 'completed', 'failed')", name='ck_research_runs_valid_status'),
        sa.CheckConstraint('length(trim(query)) > 0', name='ck_research_runs_query_nonempty'),
        sa.ForeignKeyConstraint(['requester_id'], ['users.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['workspace_id'], ['workspaces.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_research_runs_requester_created', 'research_runs', ['requester_id', 'created_at'], unique=False)
    op.create_index(op.f('ix_research_runs_requester_id'), 'research_runs', ['requester_id'], unique=False)
    op.create_index('ix_research_runs_workspace_created', 'research_runs', ['workspace_id', 'created_at'], unique=False)
    op.create_index(op.f('ix_research_runs_workspace_id'), 'research_runs', ['workspace_id'], unique=False)
    op.create_index('ix_research_runs_workspace_status', 'research_runs', ['workspace_id', 'status'], unique=False)

    op.create_table(
        'research_run_documents',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('research_run_id', sa.Integer(), nullable=False),
        sa.Column('document_id', sa.Integer(), nullable=False),
        sa.Column('provenance', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['document_id'], ['documents.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['research_run_id'], ['research_runs.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('research_run_id', 'document_id', name='uq_research_run_documents_run_document')
    )
    op.create_index('ix_research_run_documents_document', 'research_run_documents', ['document_id'], unique=False)


def downgrade() -> None:
    op.drop_index('ix_research_run_documents_document', table_name='research_run_documents')
    op.drop_table('research_run_documents')
    op.drop_index('ix_research_runs_workspace_status', table_name='research_runs')
    op.drop_index(op.f('ix_research_runs_workspace_id'), table_name='research_runs')
    op.drop_index('ix_research_runs_workspace_created', table_name='research_runs')
    op.drop_index(op.f('ix_research_runs_requester_id'), table_name='research_runs')
    op.drop_index('ix_research_runs_requester_created', table_name='research_runs')
    op.drop_table('research_runs')
