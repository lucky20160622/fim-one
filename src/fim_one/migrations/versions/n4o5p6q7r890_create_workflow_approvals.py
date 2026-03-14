"""create workflow_approvals table

Revision ID: n4o5p6q7r890
Revises: m3n4o5p6q789
Create Date: 2026-03-14
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

from fim_one.migrations.helpers import table_exists

revision: str = "n4o5p6q7r890"
down_revision: Union[str, None] = "m3n4o5p6q789"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()

    if not table_exists(bind, "workflow_approvals"):
        op.create_table(
            "workflow_approvals",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column(
                "workflow_run_id",
                sa.String(36),
                sa.ForeignKey("workflow_runs.id", ondelete="CASCADE"),
                nullable=False,
                index=True,
            ),
            sa.Column("node_id", sa.String(100), nullable=False),
            sa.Column("title", sa.String(500), nullable=False),
            sa.Column("description", sa.Text, nullable=True),
            sa.Column("assignee", sa.String(36), nullable=True, index=True),
            sa.Column(
                "status",
                sa.String(20),
                nullable=False,
                server_default="pending",
            ),
            sa.Column("decision_by", sa.String(36), nullable=True),
            sa.Column("decision_note", sa.Text, nullable=True),
            sa.Column("timeout_hours", sa.Float, nullable=False, server_default="24"),
            sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.text("(CURRENT_TIMESTAMP)"),
                nullable=False,
            ),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        )


def downgrade() -> None:
    op.drop_table("workflow_approvals")
