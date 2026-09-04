"""Initialize todo items.

Revision ID: 9d42e8b701fc
Revises:
Created: 2026-09-04
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "9d42e8b701fc"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = ("todo_list",)
depends_on: str | Sequence[str] | None = None


def upgrade(name: str = "") -> None:
    if name:
        return
    op.create_table(
        "todo_item",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("checked", sa.Boolean(), nullable=False),
        sa.Column("pinned", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_todo_item")),
        info={"bind_key": "todo_list"},
    )
    op.create_index(
        op.f("ix_todo_item_user_id"),
        "todo_item",
        ["user_id"],
        unique=False,
    )


def downgrade(name: str = "") -> None:
    if name:
        return
    op.drop_index(op.f("ix_todo_item_user_id"), table_name="todo_item")
    op.drop_table("todo_item")
