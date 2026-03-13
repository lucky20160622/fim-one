"""Add review_log audit trail table.

Revision ID: d5e6f7a8b901
Revises: c4d5e6
Create Date: 2026-03-13
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "d5e6f7a8b901"
down_revision = "c4d5e6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()

    from fim_one.migrations.helpers import index_exists, table_exists

    if table_exists(bind, "review_log"):
        return

    op.create_table(
        "review_log",
        sa.Column("id", sa.String, primary_key=True),
        sa.Column("org_id", sa.String, nullable=False),
        sa.Column("resource_type", sa.String, nullable=False),
        sa.Column("resource_id", sa.String, nullable=False),
        sa.Column("resource_name", sa.String, nullable=False),
        sa.Column("action", sa.String, nullable=False),
        sa.Column("actor_id", sa.String, nullable=True),
        sa.Column("actor_username", sa.String, nullable=True),
        sa.Column("note", sa.Text, nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime,
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
    )

    if not index_exists(bind, "review_log", "ix_review_log_org_id"):
        op.create_index("ix_review_log_org_id", "review_log", ["org_id"])

    if not index_exists(bind, "review_log", "ix_review_log_resource_id"):
        op.create_index("ix_review_log_resource_id", "review_log", ["resource_id"])


def downgrade() -> None:
    op.drop_table("review_log")
