"""Add per-device connect_timeout and command_timeout columns.

Revision ID: 0010
Revises: 0009
Create Date: 2026-05-07
"""
from alembic import op
import sqlalchemy as sa

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("devices", sa.Column("connect_timeout", sa.Integer(), nullable=True))
    op.add_column("devices", sa.Column("command_timeout", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("devices", "command_timeout")
    op.drop_column("devices", "connect_timeout")
