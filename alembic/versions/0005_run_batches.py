"""add run_batches table and link runs/devices

Revision ID: 0005_run_batches
Revises: 0004_cve_tables
Create Date: 2026-05-07

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0005_run_batches"
down_revision: Union[str, None] = "0004_cve_tables"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "run_batches",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("schedule_id", sa.Integer(), nullable=True),
        sa.Column("schedule_name", sa.String(128), nullable=False),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("total", sa.Integer(), nullable=False),
        sa.Column("succeeded", sa.Integer(), server_default="0", nullable=False),
        sa.Column("failed", sa.Integer(), server_default="0", nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("commit_sha", sa.String(64), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["schedule_id"], ["schedules.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_run_batches_started_at", "run_batches", ["started_at"])

    op.add_column("runs", sa.Column("batch_id", sa.Integer(), nullable=True))
    op.create_foreign_key(
        "fk_runs_batch_id",
        "runs",
        "run_batches",
        ["batch_id"],
        ["id"],
        ondelete="SET NULL",
    )

    op.add_column(
        "devices", sa.Column("latest_backup_path", sa.String(512), nullable=True)
    )
    op.add_column(
        "devices",
        sa.Column("latest_backup_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("devices", "latest_backup_at")
    op.drop_column("devices", "latest_backup_path")
    op.drop_constraint("fk_runs_batch_id", "runs", type_="foreignkey")
    op.drop_column("runs", "batch_id")
    op.drop_index("ix_run_batches_started_at", table_name="run_batches")
    op.drop_table("run_batches")
