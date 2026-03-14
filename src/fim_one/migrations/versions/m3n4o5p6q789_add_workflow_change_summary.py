"""add workflow change_summary column

Revision ID: m3n4o5p6q789
Revises: z4a6b8c0d123
Create Date: 2026-03-14
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

from fim_one.migrations.helpers import table_exists, table_has_column

revision: str = "m3n4o5p6q789"
down_revision: Union[str, None] = "z4a6b8c0d123"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()

    if table_exists(bind, "workflows") and not table_has_column(
        bind, "workflows", "change_summary"
    ):
        op.add_column(
            "workflows",
            sa.Column("change_summary", sa.Text, nullable=True),
        )


def downgrade() -> None:
    op.drop_column("workflows", "change_summary")
