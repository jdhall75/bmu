"""Convert Device from single group_id to many-to-many group membership.

Revision ID: 0011_device_many_groups
Revises: 0010_device_timeouts
Create Date: 2026-05-11
"""

from alembic import op
import sqlalchemy as sa

revision = "0011_device_many_groups"
down_revision = "0010_device_timeouts"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "device_group_memberships",
        sa.Column("device_id", sa.Integer(), nullable=False),
        sa.Column("device_group_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["device_id"], ["devices.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["device_group_id"], ["device_groups.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("device_id", "device_group_id"),
    )
    # Migrate existing single-group memberships into the junction table.
    op.execute("""
        INSERT INTO device_group_memberships (device_id, device_group_id)
        SELECT id, group_id FROM devices
        WHERE group_id IS NOT NULL
    """)
    op.drop_constraint("devices_group_id_fkey", "devices", type_="foreignkey")
    op.drop_column("devices", "group_id")


def downgrade() -> None:
    op.add_column("devices", sa.Column("group_id", sa.Integer(), nullable=True))
    op.create_foreign_key(
        "devices_group_id_fkey",
        "devices",
        "device_groups",
        ["group_id"],
        ["id"],
        ondelete="CASCADE",
    )
    # Restore first group as the canonical group_id.
    op.execute("""
        UPDATE devices d
        SET group_id = (
            SELECT device_group_id
            FROM device_group_memberships dgm
            WHERE dgm.device_id = d.id
            ORDER BY device_group_id
            LIMIT 1
        )
    """)
    op.drop_table("device_group_memberships")
