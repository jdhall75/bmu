"""Add worker_pool to devices and device_groups

Revision ID: 0020_worker_pool
Revises: 0019_compliance
Create Date: 2026-05-14

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0020_worker_pool"
down_revision: Union[str, None] = "0019_compliance"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "devices",
        sa.Column("worker_pool", sa.String(64), nullable=True),
    )
    op.create_index("ix_devices_worker_pool", "devices", ["worker_pool"])

    op.add_column(
        "device_groups",
        sa.Column("worker_pool", sa.String(64), nullable=True),
    )


def downgrade() -> None:
    op.drop_index("ix_devices_worker_pool", table_name="devices")
    op.drop_column("devices", "worker_pool")
    op.drop_column("device_groups", "worker_pool")
