"""Add allow_fallback to mcp_servers and create mcp_server_credentials table.

Revision ID: u1v3x5z7a890
Revises: s9u1w3y5a678
Create Date: 2026-03-13
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

from fim_one.migrations.helpers import table_exists, table_has_column, index_exists

revision = "u1v3x5z7a890"
down_revision = "s9u1w3y5a678"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()

    # 1. Add allow_fallback to mcp_servers
    if not table_has_column(bind, "mcp_servers", "allow_fallback"):
        with op.batch_alter_table("mcp_servers") as batch_op:
            batch_op.add_column(
                sa.Column(
                    "allow_fallback",
                    sa.Boolean(),
                    nullable=False,
                    server_default=sa.text("TRUE"),
                )
            )

    # 2. Create mcp_server_credentials table
    if not table_exists(bind, "mcp_server_credentials"):
        op.create_table(
            "mcp_server_credentials",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column(
                "server_id",
                sa.String(36),
                sa.ForeignKey("mcp_servers.id", ondelete="CASCADE"),
                nullable=False,
                index=True,
            ),
            sa.Column(
                "user_id",
                sa.String(36),
                sa.ForeignKey("users.id", ondelete="CASCADE"),
                nullable=True,
                index=True,
            ),
            sa.Column("env_blob", sa.Text(), nullable=True),
            sa.Column("headers_blob", sa.Text(), nullable=True),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.text("(CURRENT_TIMESTAMP)"),
            ),
            sa.Column(
                "updated_at",
                sa.DateTime(timezone=True),
                nullable=True,
            ),
            sa.UniqueConstraint(
                "server_id", "user_id", name="uq_mcp_server_user_credential"
            ),
        )


def downgrade() -> None:
    bind = op.get_bind()

    if table_exists(bind, "mcp_server_credentials"):
        op.drop_table("mcp_server_credentials")

    if table_has_column(bind, "mcp_servers", "allow_fallback"):
        with op.batch_alter_table("mcp_servers") as batch_op:
            batch_op.drop_column("allow_fallback")
