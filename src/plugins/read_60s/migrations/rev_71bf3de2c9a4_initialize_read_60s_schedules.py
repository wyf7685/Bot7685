"""Initialize read 60s schedules.

Revision ID: 71bf3de2c9a4
Revises:
Created: 2026-09-04
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "71bf3de2c9a4"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = ("read_60s",)
depends_on: str | Sequence[str] | None = None


def upgrade(name: str = "") -> None:
    if name:
        return
    op.create_table(
        "read_60s_schedule",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("session_persist_id", sa.Integer(), nullable=False),
        sa.Column("scene_persist_id", sa.Integer(), nullable=False),
        sa.Column("hour", sa.Integer(), nullable=False),
        sa.Column("minute", sa.Integer(), nullable=False),
        sa.CheckConstraint(
            "hour BETWEEN 0 AND 23",
            name=op.f("ck_read_60s_schedule_valid_hour"),
        ),
        sa.CheckConstraint(
            "minute BETWEEN 0 AND 59",
            name=op.f("ck_read_60s_schedule_valid_minute"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_read_60s_schedule")),
        sa.UniqueConstraint(
            "scene_persist_id",
            "hour",
            "minute",
            name=op.f("uq_read_60s_schedule_scene_persist_id"),
        ),
        info={"bind_key": "read_60s"},
    )
    op.create_index(
        op.f("ix_read_60s_schedule_scene_persist_id"),
        "read_60s_schedule",
        ["scene_persist_id"],
        unique=False,
    )


def downgrade(name: str = "") -> None:
    if name:
        return
    op.drop_index(
        op.f("ix_read_60s_schedule_scene_persist_id"),
        table_name="read_60s_schedule",
    )
    op.drop_table("read_60s_schedule")
