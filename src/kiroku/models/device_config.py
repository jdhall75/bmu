from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from kiroku.db.base import Base


class DeviceConfig(Base):
    __tablename__ = "device_configs"

    device_id: Mapped[int] = mapped_column(
        ForeignKey("devices.id", ondelete="CASCADE"), primary_key=True
    )
    batch_id: Mapped[int | None] = mapped_column(
        ForeignKey("run_batches.id", ondelete="SET NULL"), nullable=True
    )
    captured_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    content: Mapped[str | None] = mapped_column(Text, nullable=True)
    # content_fts (tsvector) populated via raw SQL upsert — not mapped here

    device = relationship("Device")
    batch = relationship("RunBatch")
