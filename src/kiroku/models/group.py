from sqlalchemy import ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from kiroku.db.base import Base, TimestampMixin


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

    devices = relationship(
        "Device", back_populates="group", cascade="all, delete-orphan"
    )
    schedules = relationship(
        "Schedule", back_populates="group", cascade="all, delete-orphan"
    )
