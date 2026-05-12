"""Add make, model, role metadata columns to devices.

Revision ID: 0014_device_metadata
Revises: 0013_credential_default
Create Date: 2026-05-12
"""
from alembic import op
import sqlalchemy as sa

revision = "0014_device_metadata"
down_revision = "0013_credential_default"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("devices", sa.Column("make", sa.String(128), nullable=True))
    op.add_column("devices", sa.Column("model", sa.String(128), nullable=True))
    op.add_column("devices", sa.Column("role", sa.String(64), nullable=True))
    op.create_index("ix_devices_make", "devices", ["make"])
    op.create_index("ix_devices_model", "devices", ["model"])
    op.create_index("ix_devices_role", "devices", ["role"])


def downgrade() -> None:
    op.drop_index("ix_devices_role", table_name="devices")
    op.drop_index("ix_devices_model", table_name="devices")
    op.drop_index("ix_devices_make", table_name="devices")
    op.drop_column("devices", "role")
    op.drop_column("devices", "model")
    op.drop_column("devices", "make")
