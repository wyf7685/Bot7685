"""initialize S3 temporary-object storage

迁移 ID: 5b7e9a2c41d0
父迁移:
创建时间: 2026-08-31
"""

from typing import TYPE_CHECKING

import sqlalchemy as sa
from alembic import op

if TYPE_CHECKING:
    from collections.abc import Sequence

revision: str = "5b7e9a2c41d0"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = ("s3",)
depends_on: str | Sequence[str] | None = None


def upgrade(name: str = "") -> None:
    if name:
        return
    op.create_table(
        "s3_temporary_object",
        sa.Column("namespace", sa.TEXT(), nullable=False),
        sa.Column("key", sa.TEXT(), nullable=False),
        sa.Column("expire_at", sa.FLOAT(), nullable=False),
        sa.PrimaryKeyConstraint(
            "namespace",
            "key",
            name=op.f("pk_s3_temporary_object"),
        ),
        info={"bind_key": "s3"},
    )


def downgrade(name: str = "") -> None:
    if name:
        return
    op.drop_table("s3_temporary_object")
