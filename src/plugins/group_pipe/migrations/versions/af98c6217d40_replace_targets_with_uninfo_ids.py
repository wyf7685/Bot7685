"""Replace persisted targets with uninfo IDs.

Revision ID: af98c6217d40
Revises: c79483f13a77
Created: 2026-09-04
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "af98c6217d40"
down_revision: str | Sequence[str] | None = "c79483f13a77"
branch_labels: str | Sequence[str] | None = ("group_pipe",)
depends_on: str | Sequence[str] | None = None


def upgrade(name: str = "") -> None:
    if name:
        return
    op.drop_table("group_pipe_pipe")
    op.create_table(
        "group_pipe_pipe",
        sa.Column("listen_scene_persist_id", sa.Integer(), nullable=False),
        sa.Column("target_scene_persist_id", sa.Integer(), nullable=False),
        sa.Column("listen_session_persist_id", sa.Integer(), nullable=False),
        sa.Column("target_session_persist_id", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint(
            "listen_scene_persist_id",
            "target_scene_persist_id",
            name=op.f("pk_group_pipe_pipe"),
        ),
        info={"bind_key": "group_pipe"},
    )


def downgrade(name: str = "") -> None:
    if name:
        return
    op.drop_table("group_pipe_pipe")
    op.create_table(
        "group_pipe_pipe",
        sa.Column("listen", sa.Integer(), nullable=False),
        sa.Column("target", sa.Integer(), nullable=False),
        sa.Column("listen_t", sa.JSON(), nullable=False),
        sa.Column("target_t", sa.JSON(), nullable=False),
        sa.PrimaryKeyConstraint(
            "listen",
            "target",
            name=op.f("pk_group_pipe_pipe"),
        ),
        info={"bind_key": "group_pipe"},
    )
