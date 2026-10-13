"""create workspaces and memberships

Revision ID: 8408ff62ae6d
Revises: bc2cc3cfac88
Create Date: 2026-10-11 09:55:51.718149

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '8408ff62ae6d'
down_revision: Union[str, Sequence[str], None] = 'bc2cc3cfac88'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'workspaces',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=120), nullable=False),
        sa.Column('created_by', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['created_by'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_workspaces_created_by'), 'workspaces', ['created_by'], unique=False)
    op.create_index('ix_workspaces_created_by_id', 'workspaces', ['created_by', 'id'], unique=False)

    op.create_table(
        'workspace_memberships',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('workspace_id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('role', sa.String(length=20), server_default='researcher', nullable=False),
        sa.Column('status', sa.String(length=20), server_default='active', nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.CheckConstraint("role IN ('owner', 'admin', 'researcher', 'viewer')", name='ck_workspace_memberships_role'),
        sa.CheckConstraint("status IN ('active', 'invited')", name='ck_workspace_memberships_status'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['workspace_id'], ['workspaces.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('workspace_id', 'user_id', name='uq_workspace_memberships_workspace_user')
    )
    op.create_index('ix_workspace_memberships_user_status', 'workspace_memberships', ['user_id', 'status'], unique=False)
    op.create_index('ix_workspace_memberships_workspace_status', 'workspace_memberships', ['workspace_id', 'status'], unique=False)

    op.create_table(
        'workspace_documents',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('workspace_id', sa.Integer(), nullable=False),
        sa.Column('document_id', sa.Integer(), nullable=False),
        sa.Column('added_by', sa.Integer(), nullable=False),
        sa.Column('added_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['added_by'], ['users.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['document_id'], ['documents.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['workspace_id'], ['workspaces.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('workspace_id', 'document_id', name='uq_workspace_documents_workspace_document')
    )
    op.create_index('ix_workspace_documents_document', 'workspace_documents', ['document_id'], unique=False)
    op.create_index('ix_workspace_documents_workspace_added', 'workspace_documents', ['workspace_id', 'added_at'], unique=False)


def downgrade() -> None:
    op.drop_index('ix_workspace_documents_workspace_added', table_name='workspace_documents')
    op.drop_index('ix_workspace_documents_document', table_name='workspace_documents')
    op.drop_table('workspace_documents')

    op.drop_index('ix_workspace_memberships_workspace_status', table_name='workspace_memberships')
    op.drop_index('ix_workspace_memberships_user_status', table_name='workspace_memberships')
    op.drop_table('workspace_memberships')

    op.drop_index('ix_workspaces_created_by_id', table_name='workspaces')
    op.drop_index(op.f('ix_workspaces_created_by'), table_name='workspaces')
    op.drop_table('workspaces')
