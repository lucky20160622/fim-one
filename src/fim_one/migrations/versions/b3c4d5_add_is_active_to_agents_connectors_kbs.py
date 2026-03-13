"""Add is_active to agents, connectors, and knowledge_bases.

Revision ID: b3c4d5
Revises: a1b2c3
Create Date: 2026-03-13
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "b3c4d5"
down_revision = "a1b2c3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()

    from fim_one.migrations.helpers import table_exists, table_has_column

    # agents.is_active
    if table_exists(bind, "agents") and not table_has_column(bind, "agents", "is_active"):
        with op.batch_alter_table("agents") as batch_op:
            batch_op.add_column(
                sa.Column(
                    "is_active",
                    sa.Boolean(),
                    nullable=False,
                    server_default=sa.text("TRUE"),
                )
            )

    # connectors.is_active
    if table_exists(bind, "connectors") and not table_has_column(bind, "connectors", "is_active"):
        with op.batch_alter_table("connectors") as batch_op:
            batch_op.add_column(
                sa.Column(
                    "is_active",
                    sa.Boolean(),
                    nullable=False,
                    server_default=sa.text("TRUE"),
                )
            )

    # knowledge_bases.is_active
    if table_exists(bind, "knowledge_bases") and not table_has_column(bind, "knowledge_bases", "is_active"):
        with op.batch_alter_table("knowledge_bases") as batch_op:
            batch_op.add_column(
                sa.Column(
                    "is_active",
                    sa.Boolean(),
                    nullable=False,
                    server_default=sa.text("TRUE"),
                )
            )


def downgrade() -> None:
    bind = op.get_bind()

    from fim_one.migrations.helpers import table_exists, table_has_column

    if table_exists(bind, "knowledge_bases") and table_has_column(bind, "knowledge_bases", "is_active"):
        with op.batch_alter_table("knowledge_bases") as batch_op:
            batch_op.drop_column("is_active")

    if table_exists(bind, "connectors") and table_has_column(bind, "connectors", "is_active"):
        with op.batch_alter_table("connectors") as batch_op:
            batch_op.drop_column("is_active")

    if table_exists(bind, "agents") and table_has_column(bind, "agents", "is_active"):
        with op.batch_alter_table("agents") as batch_op:
            batch_op.drop_column("is_active")
