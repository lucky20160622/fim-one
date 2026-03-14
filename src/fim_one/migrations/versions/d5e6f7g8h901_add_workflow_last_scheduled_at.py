"""add last_scheduled_at to workflows for scheduler tracking

Revision ID: d5e6f7g8h901
Revises: c4d5e6f7g890
Create Date: 2026-03-14
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

from fim_one.migrations.helpers import table_exists, table_has_column

revision: str = "d5e6f7g8h901"
down_revision: Union[str, None] = "c4d5e6f7g890"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()

    if not table_exists(bind, "workflows"):
        return

    if not table_has_column(bind, "workflows", "last_scheduled_at"):
        op.add_column(
            "workflows",
            sa.Column(
                "last_scheduled_at",
                sa.DateTime(timezone=True),
                nullable=True,
            ),
        )


def downgrade() -> None:
    op.drop_column("workflows", "last_scheduled_at")
