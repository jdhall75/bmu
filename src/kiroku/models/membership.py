from sqlalchemy import Column, ForeignKey, Table

from kiroku.db.base import Base

device_group_memberships = Table(
    "device_group_memberships",
    Base.metadata,
    Column("device_id", ForeignKey("devices.id", ondelete="CASCADE"), primary_key=True),
    Column(
        "device_group_id",
        ForeignKey("device_groups.id", ondelete="CASCADE"),
        primary_key=True,
    ),
)
