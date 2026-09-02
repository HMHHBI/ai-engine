"""add_reset_token_hash_and_expiry

Revision ID: 7a99b1a5acae
Revises: d3ba22db292b
Create Date: 2026-09-01 06:48:21.427256

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "7a99b1a5acae"
down_revision: Union[str, Sequence[str], None] = "d3ba22db292b"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Enum type safely handle karein
    op.execute(
        "DO $$ BEGIN CREATE TYPE user_plan AS ENUM ('FREE', 'STANDARD', 'PRO'); EXCEPTION WHEN duplicate_object THEN null; END $$;"
    )

    # 2. ai_logs table update
    op.alter_column("ai_logs", "task", existing_type=sa.VARCHAR(), nullable=False)
    op.alter_column(
        "ai_logs",
        "created_at",
        existing_type=postgresql.TIMESTAMP(),
        type_=sa.DateTime(timezone=True),
        nullable=False,
    )
    op.create_index(op.f("ix_ai_logs_user_id"), "ai_logs", ["user_id"], unique=False)
    op.create_foreign_key(
        None, "ai_logs", "users", ["user_id"], ["id"], ondelete="SET NULL"
    )

    # 3. chats table update
    op.alter_column("chats", "user_id", existing_type=sa.INTEGER(), nullable=False)
    op.alter_column("chats", "title", existing_type=sa.VARCHAR(), nullable=False)
    op.create_index(op.f("ix_chats_user_id"), "chats", ["user_id"], unique=False)
    op.create_index("ix_chats_user_id_id", "chats", ["user_id", "id"], unique=False)
    op.drop_constraint(op.f("chats_user_id_fkey"), "chats", type_="foreignkey")
    op.create_foreign_key(
        None, "chats", "users", ["user_id"], ["id"], ondelete="CASCADE"
    )

    # 4. document_chunks table update
    op.alter_column(
        "document_chunks",
        "created_at",
        existing_type=postgresql.TIMESTAMP(),
        type_=sa.DateTime(timezone=True),
        nullable=False,
    )
    op.create_index(
        op.f("ix_document_chunks_chat_id"), "document_chunks", ["chat_id"], unique=False
    )
    op.create_index(
        "ix_document_chunks_chat_id_id",
        "document_chunks",
        ["chat_id", "id"],
        unique=False,
    )

    # 5. messages table update
    op.alter_column("messages", "chat_id", existing_type=sa.INTEGER(), nullable=False)
    op.alter_column("messages", "role", existing_type=sa.VARCHAR(), nullable=False)
    op.alter_column("messages", "content", existing_type=sa.TEXT(), nullable=False)
    op.alter_column(
        "messages",
        "created_at",
        existing_type=postgresql.TIMESTAMP(),
        type_=sa.DateTime(timezone=True),
        nullable=False,
    )
    op.create_index(op.f("ix_messages_chat_id"), "messages", ["chat_id"], unique=False)
    op.create_index(
        "ix_messages_chat_id_id", "messages", ["chat_id", "id"], unique=False
    )
    op.drop_constraint(op.f("messages_chat_id_fkey"), "messages", type_="foreignkey")
    op.create_foreign_key(
        None, "messages", "chats", ["chat_id"], ["id"], ondelete="CASCADE"
    )

    # 6. users table updates (Password reset security + defaults)
    op.add_column(
        "users", sa.Column("reset_token_hash", sa.String(length=64), nullable=True)
    )
    op.add_column(
        "users",
        sa.Column("reset_token_expires_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "users",
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )

    # Safe cast from old enum/string to new user_plan enum
    op.execute(
        "ALTER TABLE users ALTER COLUMN plan TYPE user_plan USING plan::text::user_plan;"
    )
    op.alter_column("users", "plan", nullable=False)

    op.alter_column("users", "image_limit", existing_type=sa.INTEGER(), nullable=False)
    op.alter_column("users", "search_limit", existing_type=sa.INTEGER(), nullable=False)
    op.alter_column("users", "is_active", existing_type=sa.BOOLEAN(), nullable=False)
    op.create_index(
        op.f("ix_users_reset_token_hash"), "users", ["reset_token_hash"], unique=True
    )
    op.drop_column("users", "reset_token")


def downgrade() -> None:
    op.add_column(
        "users",
        sa.Column("reset_token", sa.VARCHAR(), autoincrement=False, nullable=True),
    )
    op.drop_index(op.f("ix_users_reset_token_hash"), table_name="users")
    op.alter_column("users", "is_active", existing_type=sa.BOOLEAN(), nullable=True)
    op.alter_column("users", "search_limit", existing_type=sa.INTEGER(), nullable=True)
    op.alter_column("users", "image_limit", existing_type=sa.INTEGER(), nullable=True)
    op.drop_column("users", "created_at")
    op.drop_column("users", "reset_token_expires_at")
    op.drop_column("users", "reset_token_hash")
    op.drop_constraint(None, "messages", type_="foreignkey")
    op.create_foreign_key(
        op.f("messages_chat_id_fkey"), "messages", "chats", ["chat_id"], ["id"]
    )
    op.drop_index("ix_messages_chat_id_id", table_name="messages")
    op.drop_index(op.f("ix_messages_chat_id"), table_name="messages")
    op.alter_column(
        "messages",
        "created_at",
        existing_type=sa.DateTime(timezone=True),
        type_=postgresql.TIMESTAMP(),
        nullable=True,
    )
    op.alter_column("messages", "content", existing_type=sa.TEXT(), nullable=True)
    op.alter_column("messages", "role", existing_type=sa.VARCHAR(), nullable=True)
    op.alter_column("messages", "chat_id", existing_type=sa.INTEGER(), nullable=True)
    op.drop_index("ix_document_chunks_chat_id_id", table_name="document_chunks")
    op.drop_index(op.f("ix_document_chunks_chat_id"), table_name="document_chunks")
    op.alter_column(
        "document_chunks",
        "created_at",
        existing_type=sa.DateTime(timezone=True),
        type_=postgresql.TIMESTAMP(),
        nullable=True,
    )
    op.drop_constraint(None, "chats", type_="foreignkey")
    op.create_foreign_key(
        op.f("chats_user_id_fkey"), "chats", "users", ["user_id"], ["id"]
    )
    op.drop_index("ix_chats_user_id_id", table_name="chats")
    op.drop_index(op.f("ix_chats_user_id"), table_name="chats")
    op.alter_column("chats", "title", existing_type=sa.VARCHAR(), nullable=True)
    op.alter_column("chats", "user_id", existing_type=sa.INTEGER(), nullable=True)
    op.drop_constraint(None, "ai_logs", type_="foreignkey")
    op.drop_index(op.f("ix_ai_logs_user_id"), table_name="ai_logs")
    op.alter_column(
        "ai_logs",
        "created_at",
        existing_type=sa.DateTime(timezone=True),
        type_=postgresql.TIMESTAMP(),
        nullable=True,
    )
    op.alter_column("ai_logs", "task", existing_type=sa.VARCHAR(), nullable=True)
