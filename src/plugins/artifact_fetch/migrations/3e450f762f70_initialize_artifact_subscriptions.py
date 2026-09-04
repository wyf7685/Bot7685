"""Initialize artifact subscriptions.

Revision ID: 3e450f762f70
Revises:
Created: 2026-09-04
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "3e450f762f70"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = ("artifact_fetch",)
depends_on: str | Sequence[str] | None = None


def upgrade(name: str = "") -> None:
    if name:
        return
    op.create_table(
        "artifact_fetch_subscription",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("session_persist_id", sa.Integer(), nullable=False),
        sa.Column("scene_persist_id", sa.Integer(), nullable=False),
        sa.Column("owner", sa.String(length=255), nullable=False),
        sa.Column("repo", sa.String(length=255), nullable=False),
        sa.Column("workflow_kind", sa.Integer(), nullable=False),
        sa.Column("workflow_value", sa.String(length=255), nullable=False),
        sa.Column("upload_artifacts", sa.Boolean(), nullable=False),
        sa.Column("filter_regex", sa.Text(), nullable=True),
        sa.Column("rename_template", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint(
            "id",
            name=op.f("pk_artifact_fetch_subscription"),
        ),
        sa.UniqueConstraint(
            "scene_persist_id",
            "owner",
            "repo",
            "workflow_kind",
            "workflow_value",
            name=op.f("uq_artifact_fetch_subscription_scene_persist_id"),
        ),
        info={"bind_key": "artifact_fetch"},
    )
    op.create_index(
        op.f("ix_artifact_fetch_subscription_scene_persist_id"),
        "artifact_fetch_subscription",
        ["scene_persist_id"],
        unique=False,
    )


def downgrade(name: str = "") -> None:
    if name:
        return
    op.drop_index(
        op.f("ix_artifact_fetch_subscription_scene_persist_id"),
        table_name="artifact_fetch_subscription",
    )
    op.drop_table("artifact_fetch_subscription")
