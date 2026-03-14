"""create workflow_templates table

Revision ID: y3z5a7b9c012
Revises: x2y4z6a8b901
Create Date: 2026-03-14
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

from fim_one.migrations.helpers import table_exists

revision: str = "y3z5a7b9c012"
down_revision: Union[str, None] = "x2y4z6a8b901"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()

    if not table_exists(bind, "workflow_templates"):
        op.create_table(
            "workflow_templates",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("name", sa.String(200), nullable=False),
            sa.Column("description", sa.Text, nullable=False),
            sa.Column("icon", sa.String(100), nullable=False, server_default="🔄"),
            sa.Column("category", sa.String(100), nullable=False),
            sa.Column("blueprint", sa.JSON, nullable=False),
            sa.Column(
                "is_active",
                sa.Boolean,
                nullable=False,
                server_default=sa.text("TRUE"),
            ),
            sa.Column(
                "sort_order",
                sa.Integer,
                nullable=False,
                server_default="0",
            ),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.text("(CURRENT_TIMESTAMP)"),
                nullable=False,
            ),
            sa.Column(
                "updated_at",
                sa.DateTime(timezone=True),
                nullable=True,
            ),
        )


def downgrade() -> None:
    op.drop_table("workflow_templates")
