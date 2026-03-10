"""add global agent and clone traceability fields

Revision ID: i9k1m3o5q678
Revises: h8j0l2n4p567
Create Date: 2026-03-10 10:00:00.000000
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "i9k1m3o5q678"
down_revision: Union[str, None] = "44221ea46a6e"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # --- agents table ---
    with op.batch_alter_table("agents") as batch_op:
        batch_op.alter_column("user_id", existing_type=sa.String(36), nullable=True)
        batch_op.add_column(sa.Column("is_global", sa.Boolean(), nullable=False, server_default=sa.text("FALSE")))
        batch_op.add_column(sa.Column("cloned_from_agent_id", sa.String(36), nullable=True))
        batch_op.add_column(sa.Column("cloned_from_user_id", sa.String(36), nullable=True))

    # mcp_servers.cloned_from_* columns are created in
    # a1d2e3f4g567_create_missing_tables (table didn't exist before).


def downgrade() -> None:
    with op.batch_alter_table("agents") as batch_op:
        batch_op.drop_column("cloned_from_user_id")
        batch_op.drop_column("cloned_from_agent_id")
        batch_op.drop_column("is_global")
        batch_op.alter_column("user_id", existing_type=sa.String(36), nullable=False)
