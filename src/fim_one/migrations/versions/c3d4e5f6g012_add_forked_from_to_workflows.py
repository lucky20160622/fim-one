"""add forked_from to workflows

Revision ID: c3d4e5f6g012
Revises: b2c3d4e5f901
Create Date: 2026-03-26
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

from fim_one.migrations.helpers import table_has_column

revision: str = "c3d4e5f6g012"
down_revision: Union[str, None] = "b2c3d4e5f901"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()

    if not table_has_column(bind, "workflows", "forked_from"):
        with op.batch_alter_table("workflows") as batch_op:
            batch_op.add_column(
                sa.Column("forked_from", sa.String(36), nullable=True)
            )


def downgrade() -> None:
    with op.batch_alter_table("workflows") as batch_op:
        batch_op.drop_column("forked_from")
