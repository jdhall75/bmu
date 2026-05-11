"""Add parsed_data JSON column to runs table.

Revision ID: 0012_run_parsed_data
Revises: 0011_device_many_groups
Create Date: 2026-05-11
"""
from alembic import op
import sqlalchemy as sa

revision = "0012_run_parsed_data"
down_revision = "0011_device_many_groups"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("runs", sa.Column("parsed_data", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("runs", "parsed_data")
