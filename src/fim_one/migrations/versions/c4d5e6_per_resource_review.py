"""Replace require_publish_review with per-resource review columns.

Revision ID: c4d5e6
Revises: b3c4d5
Create Date: 2026-03-13
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "c4d5e6"
down_revision = "b3c4d5"
branch_labels = None
depends_on = None

PLATFORM_ORG_ID = "00000000-0000-0000-0000-000000000001"

NEW_COLUMNS = ["review_agents", "review_connectors", "review_kbs", "review_mcp_servers"]


def upgrade() -> None:
    bind = op.get_bind()

    from fim_one.migrations.helpers import table_exists, table_has_column

    if not table_exists(bind, "organizations"):
        return

    # 1. Add the 4 new per-resource review columns
    for col_name in NEW_COLUMNS:
        if not table_has_column(bind, "organizations", col_name):
            with op.batch_alter_table("organizations") as batch_op:
                batch_op.add_column(
                    sa.Column(
                        col_name,
                        sa.Boolean(),
                        nullable=False,
                        server_default=sa.text("FALSE"),
                    )
                )

    # 2. Data migration: copy require_publish_review value to all 4 new columns
    if table_has_column(bind, "organizations", "require_publish_review"):
        for col_name in NEW_COLUMNS:
            bind.execute(
                sa.text(
                    f"UPDATE organizations SET {col_name} = require_publish_review"
                )
            )

    # 3. Set Platform org: all 4 = TRUE
    for col_name in NEW_COLUMNS:
        bind.execute(
            sa.text(
                f"UPDATE organizations SET {col_name} = TRUE"
                f" WHERE id = :platform_id"
            ),
            {"platform_id": PLATFORM_ORG_ID},
        )

    # 4. Drop the old require_publish_review column
    if table_has_column(bind, "organizations", "require_publish_review"):
        with op.batch_alter_table("organizations") as batch_op:
            batch_op.drop_column("require_publish_review")


def downgrade() -> None:
    bind = op.get_bind()

    from fim_one.migrations.helpers import table_exists, table_has_column

    if not table_exists(bind, "organizations"):
        return

    # 1. Re-add require_publish_review
    if not table_has_column(bind, "organizations", "require_publish_review"):
        with op.batch_alter_table("organizations") as batch_op:
            batch_op.add_column(
                sa.Column(
                    "require_publish_review",
                    sa.Boolean(),
                    nullable=False,
                    server_default=sa.text("FALSE"),
                )
            )

    # 2. Copy review_agents value back (best-effort; any of the 4 would do)
    if table_has_column(bind, "organizations", "review_agents"):
        bind.execute(
            sa.text(
                "UPDATE organizations SET require_publish_review = review_agents"
            )
        )

    # 3. Drop the 4 per-resource columns
    for col_name in NEW_COLUMNS:
        if table_has_column(bind, "organizations", col_name):
            with op.batch_alter_table("organizations") as batch_op:
                batch_op.drop_column(col_name)
