"""initialize S3 upload permissions

迁移 ID: 89fd3b6a20c1
父迁移:
创建时间: 2026-08-31
"""

from typing import TYPE_CHECKING

import sqlalchemy as sa
from alembic import op

if TYPE_CHECKING:
    from collections.abc import Sequence

revision: str = "89fd3b6a20c1"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = ("s3_admin",)
depends_on: str | Sequence[str] | None = None


def upgrade(name: str = "") -> None:
    if name:
        return
    op.create_table(
        "s3_upload_permission",
        sa.Column("identity", sa.TEXT(), nullable=False),
        sa.Column("expire_at", sa.FLOAT(), nullable=False),
        sa.PrimaryKeyConstraint(
            "identity",
            name=op.f("pk_s3_upload_permission"),
        ),
        info={"bind_key": "s3_admin"},
    )


def downgrade(name: str = "") -> None:
    if name:
        return
    op.drop_table("s3_upload_permission")
