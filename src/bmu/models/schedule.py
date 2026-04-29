import enum
from datetime import datetime

from sqlalchemy import Boolean, DateTime
from sqlalchemy import Enum as SAEnum
from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from bmu.db.base import Base, TimestampMixin


class JobKind(str, enum.Enum):
    BACKUP = "backup"
    COLLECT = "collect"


class Schedule(Base, TimestampMixin):
    __tablename__ = "schedules"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    group_id: Mapped[int] = mapped_column(
        ForeignKey("device_groups.id", ondelete="CASCADE"), nullable=False
    )
    group = relationship("DeviceGroup", back_populates="schedules")

    kind: Mapped[JobKind] = mapped_column(
        SAEnum(
            JobKind,
            name="job_kind",
            values_callable=lambda e: [m.value for m in e],
        ),
        nullable=False,
    )
    cron: Mapped[str] = mapped_column(String(64), nullable=False)
    timezone: Mapped[str] = mapped_column(String(64), default="UTC", nullable=False)

    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # Scheduler bookkeeping.
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    next_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
