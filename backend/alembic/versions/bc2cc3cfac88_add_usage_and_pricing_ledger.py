"""add_usage_and_pricing_ledger

Revision ID: bc2cc3cfac88
Revises: b3a490b636d1
Create Date: 2026-10-10 05:21:12.341657

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'bc2cc3cfac88'
down_revision: Union[str, Sequence[str], None] = 'b3a490b636d1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'model_pricing',
        sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('provider', sa.String(length=32), nullable=False),
        sa.Column('model', sa.String(length=128), nullable=False),
        sa.Column('currency', sa.String(length=3), nullable=False, server_default='USD'),
        sa.Column('input_rate_per_million', sa.Numeric(precision=18, scale=8), nullable=False),
        sa.Column('output_rate_per_million', sa.Numeric(precision=18, scale=8), nullable=False),
        sa.Column('cached_input_rate_per_million', sa.Numeric(precision=18, scale=8), nullable=True),
        sa.Column('pricing_version', sa.String(length=64), nullable=False),
        sa.Column('effective_from', sa.DateTime(timezone=True), nullable=False),
        sa.Column('effective_until', sa.DateTime(timezone=True), nullable=True),
        sa.Column('source_reference', sa.String(length=255), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.CheckConstraint('cached_input_rate_per_million IS NULL OR cached_input_rate_per_million >= 0', name='ck_model_pricing_cached_rate_non_negative'),
        sa.CheckConstraint('effective_until IS NULL OR effective_until > effective_from', name='ck_model_pricing_effective_range'),
        sa.CheckConstraint('input_rate_per_million >= 0', name='ck_model_pricing_input_rate_non_negative'),
        sa.CheckConstraint('output_rate_per_million >= 0', name='ck_model_pricing_output_rate_non_negative'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('provider', 'model', 'pricing_version', name='uq_model_pricing_provider_model_version')
    )
    op.create_index('ix_model_pricing_lookup', 'model_pricing', ['provider', 'model', 'effective_from', 'effective_until'], unique=False)
    op.create_index(op.f('ix_model_pricing_model'), 'model_pricing', ['model'], unique=False)
    op.create_index(op.f('ix_model_pricing_provider'), 'model_pricing', ['provider'], unique=False)

    op.create_table(
        'ai_usage_events',
        sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('request_id', sa.String(length=64), nullable=False),
        sa.Column('idempotency_key', sa.String(length=128), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=True),
        sa.Column('chat_id', sa.Integer(), nullable=True),
        sa.Column('message_id', sa.Integer(), nullable=True),
        sa.Column('provider', sa.String(length=32), nullable=False),
        sa.Column('model', sa.String(length=128), nullable=False),
        sa.Column('operation', sa.String(length=64), nullable=False, server_default='chat'),
        sa.Column('input_tokens', sa.Integer(), nullable=True),
        sa.Column('output_tokens', sa.Integer(), nullable=True),
        sa.Column('total_tokens', sa.Integer(), nullable=True),
        sa.Column('usage_source', sa.String(length=32), nullable=False, server_default='provider_reported'),
        sa.Column('status', sa.String(length=32), nullable=False, server_default='succeeded'),
        sa.Column('cost_amount', sa.Numeric(precision=18, scale=8), nullable=True),
        sa.Column('cost_currency', sa.String(length=3), nullable=True, server_default='USD'),
        sa.Column('pricing_version', sa.String(length=64), nullable=True),
        sa.Column('pricing_snapshot', sa.JSON(), nullable=True),
        sa.Column('provider_metadata', sa.JSON(), nullable=True),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.CheckConstraint('cost_amount IS NULL OR cost_amount >= 0', name='ck_ai_usage_events_cost_non_negative'),
        sa.CheckConstraint('input_tokens IS NULL OR input_tokens >= 0', name='ck_ai_usage_events_input_tokens_non_negative'),
        sa.CheckConstraint('output_tokens IS NULL OR output_tokens >= 0', name='ck_ai_usage_events_output_tokens_non_negative'),
        sa.CheckConstraint('total_tokens IS NULL OR total_tokens >= 0', name='ck_ai_usage_events_total_tokens_non_negative'),
        sa.ForeignKeyConstraint(['chat_id'], ['chats.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['message_id'], ['messages.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_ai_usage_events_chat_created', 'ai_usage_events', ['chat_id', 'created_at'], unique=False)
    op.create_index(op.f('ix_ai_usage_events_chat_id'), 'ai_usage_events', ['chat_id'], unique=False)
    op.create_index(op.f('ix_ai_usage_events_idempotency_key'), 'ai_usage_events', ['idempotency_key'], unique=True)
    op.create_index(op.f('ix_ai_usage_events_message_id'), 'ai_usage_events', ['message_id'], unique=False)
    op.create_index(op.f('ix_ai_usage_events_model'), 'ai_usage_events', ['model'], unique=False)
    op.create_index(op.f('ix_ai_usage_events_provider'), 'ai_usage_events', ['provider'], unique=False)
    op.create_index('ix_ai_usage_events_provider_model_created', 'ai_usage_events', ['provider', 'model', 'created_at'], unique=False)
    op.create_index(op.f('ix_ai_usage_events_request_id'), 'ai_usage_events', ['request_id'], unique=False)
    op.create_index('ix_ai_usage_events_user_created', 'ai_usage_events', ['user_id', 'created_at'], unique=False)
    op.create_index(op.f('ix_ai_usage_events_user_id'), 'ai_usage_events', ['user_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_ai_usage_events_user_id'), table_name='ai_usage_events')
    op.drop_index('ix_ai_usage_events_user_created', table_name='ai_usage_events')
    op.drop_index(op.f('ix_ai_usage_events_request_id'), table_name='ai_usage_events')
    op.drop_index('ix_ai_usage_events_provider_model_created', table_name='ai_usage_events')
    op.drop_index(op.f('ix_ai_usage_events_provider'), table_name='ai_usage_events')
    op.drop_index(op.f('ix_ai_usage_events_model'), table_name='ai_usage_events')
    op.drop_index(op.f('ix_ai_usage_events_message_id'), table_name='ai_usage_events')
    op.drop_index(op.f('ix_ai_usage_events_idempotency_key'), table_name='ai_usage_events')
    op.drop_index(op.f('ix_ai_usage_events_chat_id'), table_name='ai_usage_events')
    op.drop_index('ix_ai_usage_events_chat_created', table_name='ai_usage_events')
    op.drop_table('ai_usage_events')
    op.drop_index(op.f('ix_model_pricing_provider'), table_name='model_pricing')
    op.drop_index(op.f('ix_model_pricing_model'), table_name='model_pricing')
    op.drop_index('ix_model_pricing_lookup', table_name='model_pricing')
    op.drop_table('model_pricing')
