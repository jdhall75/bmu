"""Add skip_next_run to schedules

Revision ID: 0021_schedule_skip_next_run
Revises: 0020_worker_pool
Create Date: 2026-05-28

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0021_schedule_skip_next_run"
down_revision: Union[str, None] = "0020_worker_pool"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "schedules",
        sa.Column(
            "skip_next_run",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )


def downgrade() -> None:
    op.drop_column("schedules", "skip_next_run")
