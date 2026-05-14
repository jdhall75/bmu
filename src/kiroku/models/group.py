from sqlalchemy import ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from kiroku.db.base import Base, TimestampMixin
from kiroku.models.membership import device_group_memberships


class DeviceGroup(Base, TimestampMixin):
    __tablename__ = "device_groups"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Default credential applied to every device in the group unless the
    # device overrides it.
    default_credential_id: Mapped[int | None] = mapped_column(
        ForeignKey("credentials.id", ondelete="SET NULL"), nullable=True
    )
    default_credential = relationship("Credential")

    # Cap on how many devices in this group are dispatched to workers in
    # parallel for any one job. Workers will still respect their own
    # concurrency setting.
    max_parallel: Mapped[int] = mapped_column(Integer, default=8, nullable=False)

    # Worker pool that devices in this group are routed to by default.
    # Overridden by device-level worker_pool when set.
    worker_pool: Mapped[str | None] = mapped_column(String(64), nullable=True)

    devices: Mapped[list["Device"]] = relationship(
        "Device", secondary=device_group_memberships, back_populates="groups"
    )
