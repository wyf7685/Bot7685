"""Initialize analysis subscriptions.

Revision ID: 56c3f5ad9a20
Revises:
Created: 2026-09-04
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "56c3f5ad9a20"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = ("group_daily_analysis",)
depends_on: str | Sequence[str] | None = None


def upgrade(name: str = "") -> None:
    if name:
        return
    op.create_table(
        "group_daily_analysis_subscription",
        sa.Column("scene_persist_id", sa.Integer(), nullable=False),
        sa.Column("session_persist_id", sa.Integer(), nullable=False),
        sa.Column("analysis_days", sa.Integer(), nullable=False),
        sa.Column("incremental_enabled", sa.Boolean(), nullable=False),
        sa.PrimaryKeyConstraint(
            "scene_persist_id",
            name=op.f("pk_group_daily_analysis_subscription"),
        ),
        info={"bind_key": "group_daily_analysis"},
    )


def downgrade(name: str = "") -> None:
    if name:
        return
    op.drop_table("group_daily_analysis_subscription")
