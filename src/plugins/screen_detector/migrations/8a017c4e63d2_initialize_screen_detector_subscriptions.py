"""Initialize screen detector subscriptions.

Revision ID: 8a017c4e63d2
Revises:
Created: 2026-09-04
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "8a017c4e63d2"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = ("screen_detector",)
depends_on: str | Sequence[str] | None = None


def upgrade(name: str = "") -> None:
    if name:
        return
    op.create_table(
        "screen_detector_package_subscription",
        sa.Column("scene_persist_id", sa.Integer(), nullable=False),
        sa.Column("session_persist_id", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint(
            "scene_persist_id",
            name=op.f("pk_screen_detector_package_subscription"),
        ),
        info={"bind_key": "screen_detector"},
    )


def downgrade(name: str = "") -> None:
    if name:
        return
    op.drop_table("screen_detector_package_subscription")
