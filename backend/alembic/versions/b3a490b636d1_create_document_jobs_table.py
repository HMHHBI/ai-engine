"""create_document_jobs_table

Revision ID: b3a490b636d1
Revises: 6ba912c183af
Create Date: 2026-09-24 06:18:22.967352

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b3a490b636d1'
down_revision: Union[str, Sequence[str], None] = '6ba912c183af'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'document_jobs',
        sa.Column('id', sa.BigInteger(), nullable=False),
        sa.Column('document_id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('status', sa.String(length=20), server_default='queued', nullable=False),
        sa.Column('attempt', sa.Integer(), server_default='0', nullable=False),
        sa.Column('max_attempts', sa.Integer(), server_default='3', nullable=False),
        sa.Column('idempotency_key', sa.String(length=128), nullable=False),
        sa.Column('worker_id', sa.String(length=128), nullable=True),
        sa.Column('queued_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('heartbeat_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('finished_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('cancel_requested_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.CheckConstraint(
            "status IN ('queued', 'processing', 'ready', 'failed', 'cancelled')",
            name='ck_document_jobs_valid_status',
        ),
        sa.CheckConstraint(
            "attempt >= 0",
            name='ck_document_jobs_attempt_non_negative',
        ),
        sa.CheckConstraint(
            "max_attempts >= 1",
            name='ck_document_jobs_max_attempts_positive',
        ),
        sa.CheckConstraint(
            "attempt <= max_attempts",
            name='ck_document_jobs_attempt_lte_max',
        ),
        sa.ForeignKeyConstraint(['document_id'], ['documents.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('idempotency_key', name='uq_document_jobs_idempotency_key'),
    )

    op.create_index(op.f('ix_document_jobs_document_id'), 'document_jobs', ['document_id'], unique=False)
    op.create_index(op.f('ix_document_jobs_user_id'), 'document_jobs', ['user_id'], unique=False)
    op.create_index('ix_document_jobs_user_id_status', 'document_jobs', ['user_id', 'status'], unique=False)
    op.create_index('ix_document_jobs_status_queued_at', 'document_jobs', ['status', 'queued_at'], unique=False)
    op.create_index('ix_document_jobs_status_heartbeat_at', 'document_jobs', ['status', 'heartbeat_at'], unique=False)

    # Partial unique index: at most one active job ('queued', 'processing') per document
    op.create_index(
        'uq_document_jobs_active_per_document',
        'document_jobs',
        ['document_id'],
        unique=True,
        postgresql_where=sa.text("status IN ('queued', 'processing')"),
    )


def downgrade() -> None:
    op.drop_index('uq_document_jobs_active_per_document', table_name='document_jobs')
    op.drop_index('ix_document_jobs_status_heartbeat_at', table_name='document_jobs')
    op.drop_index('ix_document_jobs_status_queued_at', table_name='document_jobs')
    op.drop_index('ix_document_jobs_user_id_status', table_name='document_jobs')
    op.drop_index(op.f('ix_document_jobs_user_id'), table_name='document_jobs')
    op.drop_index(op.f('ix_document_jobs_document_id'), table_name='document_jobs')
    op.drop_table('document_jobs')
