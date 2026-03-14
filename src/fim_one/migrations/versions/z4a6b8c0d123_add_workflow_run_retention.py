"""add run_retention_days to workflows

Revision ID: z4a6b8c0d123
Revises: y3z5a7b9c012
Create Date: 2026-03-14
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

from fim_one.migrations.helpers import table_has_column

revision: str = "z4a6b8c0d123"
down_revision: Union[str, None] = "y3z5a7b9c012"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()

    if not table_has_column(bind, "workflows", "run_retention_days"):
        with op.batch_alter_table("workflows") as batch_op:
            batch_op.add_column(
                sa.Column(
                    "run_retention_days",
                    sa.Integer,
                    nullable=True,
                )
            )


def downgrade() -> None:
    with op.batch_alter_table("workflows") as batch_op:
        batch_op.drop_column("run_retention_days")
