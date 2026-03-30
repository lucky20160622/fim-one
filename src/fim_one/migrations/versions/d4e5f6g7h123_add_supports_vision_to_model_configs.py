"""add supports_vision to model_configs and model_provider_models

Revision ID: d4e5f6g7h123
Revises: c3d4e5f6g012
Create Date: 2026-03-29
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

from fim_one.migrations.helpers import table_has_column, table_exists

# revision identifiers, used by Alembic.
revision: str = "d4e5f6g7h123"
down_revision: Union[str, None] = "c3d4e5f6g012"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()

    if not table_has_column(bind, "model_configs", "supports_vision"):
        with op.batch_alter_table("model_configs") as batch_op:
            batch_op.add_column(
                sa.Column(
                    "supports_vision",
                    sa.Boolean,
                    nullable=False,
                    server_default=sa.text("FALSE"),
                )
            )

    if table_exists(bind, "model_provider_models") and not table_has_column(
        bind, "model_provider_models", "supports_vision"
    ):
        with op.batch_alter_table("model_provider_models") as batch_op:
            batch_op.add_column(
                sa.Column(
                    "supports_vision",
                    sa.Boolean,
                    nullable=False,
                    server_default=sa.text("FALSE"),
                )
            )


def downgrade() -> None:
    with op.batch_alter_table("model_configs") as batch_op:
        batch_op.drop_column("supports_vision")

    bind = op.get_bind()
    if table_exists(bind, "model_provider_models") and table_has_column(
        bind, "model_provider_models", "supports_vision"
    ):
        with op.batch_alter_table("model_provider_models") as batch_op:
            batch_op.drop_column("supports_vision")
