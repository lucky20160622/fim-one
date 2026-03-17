"""Market redesign phase 1: backfill subscriptions for skills/workflows,
re-subscribe all 6 resource types with publish_status filter.

Revision ID: m1k2t3r4d567
Revises: p7q8r9s0t123
Create Date: 2026-03-17
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "m1k2t3r4d567"
down_revision = "p7q8r9s0t123"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()

    from fim_one.migrations.helpers import table_exists, table_has_column

    if not table_exists(bind, "resource_subscriptions"):
        return
    if not table_exists(bind, "org_memberships"):
        return

    # All 6 resource types — the previous migration (t1u3v5x7z890) only
    # covered agents/connectors/knowledge_bases/mcp_servers, and did NOT
    # filter by publish_status.  This migration re-runs for all 6 types
    # with the correct filter (only approved or null publish_status).
    # Idempotent: skips rows that already have a subscription via the
    # unique constraint check.
    resource_map = {
        "agents": "agent",
        "connectors": "connector",
        "knowledge_bases": "knowledge_base",
        "mcp_servers": "mcp_server",
        "skills": "skill",
        "workflows": "workflow",
    }

    import uuid as _uuid
    from datetime import datetime as _dt, timezone as _tz

    for table, rtype in resource_map.items():
        if not table_exists(bind, table):
            continue
        if not table_has_column(bind, table, "visibility"):
            continue
        if not table_has_column(bind, table, "org_id"):
            continue

        # Build the SELECT with publish_status filter if the column exists
        has_publish_status = table_has_column(bind, table, "publish_status")
        if has_publish_status:
            query = (
                f"SELECT id, user_id, org_id FROM {table} "
                "WHERE visibility='org' AND org_id IS NOT NULL "
                "AND (publish_status IS NULL OR publish_status = 'approved')"
            )
        else:
            query = (
                f"SELECT id, user_id, org_id FROM {table} "
                "WHERE visibility='org' AND org_id IS NOT NULL"
            )

        rows = bind.execute(sa.text(query)).fetchall()

        for row in rows:
            res_id, owner_id, org_id = row[0], row[1], row[2]
            if not owner_id or not org_id:
                continue

            # Get all org members except the resource owner
            members = bind.execute(
                sa.text(
                    "SELECT user_id FROM org_memberships "
                    "WHERE org_id=:org AND user_id != :owner"
                ),
                {"org": org_id, "owner": owner_id},
            ).fetchall()

            for member_row in members:
                member_uid = member_row[0]

                # Skip if subscription already exists (idempotent)
                exists = bind.execute(
                    sa.text(
                        "SELECT id FROM resource_subscriptions "
                        "WHERE user_id=:uid AND resource_type=:rt AND resource_id=:rid"
                    ),
                    {"uid": member_uid, "rt": rtype, "rid": res_id},
                ).fetchone()

                if not exists:
                    sub_id = str(_uuid.uuid4())
                    now = _dt.now(_tz.utc).isoformat()
                    bind.execute(
                        sa.text(
                            "INSERT INTO resource_subscriptions "
                            "(id, user_id, resource_type, resource_id, org_id, created_at) "
                            "VALUES (:id, :uid, :rt, :rid, :org, :now)"
                        ),
                        {
                            "id": sub_id,
                            "uid": member_uid,
                            "rt": rtype,
                            "rid": res_id,
                            "org": org_id,
                            "now": now,
                        },
                    )


def downgrade() -> None:
    """Downgrade is not supported — data migration only."""
    pass
