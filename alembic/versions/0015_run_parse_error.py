"""Add parse_error column to runs.

Revision ID: 0015_run_parse_error
Revises: 0014_device_metadata
Create Date: 2026-05-12
"""
from alembic import op
import sqlalchemy as sa

revision = "0015_run_parse_error"
down_revision = "0014_device_metadata"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("runs", sa.Column("parse_error", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("runs", "parse_error")
