from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from kiroku.db.base import Base, TimestampMixin


class Device(Base, TimestampMixin):
    __tablename__ = "devices"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    hostname: Mapped[str] = mapped_column(String(255), nullable=False)
    port: Mapped[int | None] = mapped_column(Integer, nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    group_id: Mapped[int] = mapped_column(
        ForeignKey("device_groups.id", ondelete="CASCADE"), nullable=False
    )
    group = relationship("DeviceGroup", back_populates="devices")

    profile_id: Mapped[int] = mapped_column(
        ForeignKey("profiles.id", ondelete="RESTRICT"), nullable=False
    )
    profile = relationship("Profile")

    # Per-device credential override; falls back to the group's default.
    credential_id: Mapped[int | None] = mapped_column(
        ForeignKey("credentials.id", ondelete="SET NULL"), nullable=True
    )
    credential = relationship("Credential")

    enabled: Mapped[bool] = mapped_column(default=True, nullable=False)

    latest_backup_path: Mapped[str | None] = mapped_column(String(512), nullable=True)
    latest_backup_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
