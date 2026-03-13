"""add review_workflows to organizations

Revision ID: x2y3z4a5b678
Revises: w1x2y3z4a567
Create Date: 2026-03-14
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

from fim_one.migrations.helpers import table_exists, table_has_column

revision: str = "x2y3z4a5b678"
down_revision: Union[str, None] = "w1x2y3z4a567"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()

    if table_exists(bind, "organizations") and not table_has_column(
        bind, "organizations", "review_workflows"
    ):
        op.add_column(
            "organizations",
            sa.Column(
                "review_workflows",
                sa.Boolean,
                nullable=False,
                server_default=sa.text("FALSE"),
            ),
        )


def downgrade() -> None:
    op.drop_column("organizations", "review_workflows")
