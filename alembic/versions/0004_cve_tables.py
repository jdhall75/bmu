"""add cve_scans and cve_results tables

Revision ID: 0004_cve_tables
Revises: 0003_cve_scan_job_kind
Create Date: 2026-05-06

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0004_cve_tables"
down_revision: Union[str, None] = "0003_cve_scan_job_kind"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "cve_scans",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("run_id", sa.Integer(), nullable=True),
        sa.Column("device_id", sa.Integer(), nullable=False),
        sa.Column("cpe", sa.String(256), nullable=False),
        sa.Column("version_found", sa.String(128), nullable=True),
        sa.Column("raw_version", sa.String(128), nullable=True),
        sa.Column("scanned_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["device_id"], ["devices.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["run_id"], ["runs.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "cve_results",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("scan_id", sa.Integer(), nullable=False),
        sa.Column("cve_id", sa.String(32), nullable=False),
        sa.Column("cvss_v3_score", sa.Numeric(4, 1), nullable=True),
        sa.Column("severity", sa.String(16), nullable=True),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("url", sa.String(512), nullable=True),
        sa.ForeignKeyConstraint(["scan_id"], ["cve_scans.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("cve_results")
    op.drop_table("cve_scans")
