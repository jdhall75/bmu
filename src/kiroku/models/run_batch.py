from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from kiroku.db.base import Base, TimestampMixin


class RunBatch(Base, TimestampMixin):
    """One firing of a schedule — groups all per-device Run rows together."""

    __tablename__ = "run_batches"

    id: Mapped[int] = mapped_column(primary_key=True)
    schedule_id: Mapped[int | None] = mapped_column(
        ForeignKey("schedules.id", ondelete="SET NULL"), nullable=True
    )
    schedule_name: Mapped[str] = mapped_column(String(128), nullable=False)
    kind: Mapped[str] = mapped_column(String(16), nullable=False)

    total: Mapped[int] = mapped_column(Integer, nullable=False)
    succeeded: Mapped[int] = mapped_column(Integer, server_default="0", nullable=False)
    failed: Mapped[int] = mapped_column(Integer, server_default="0", nullable=False)

    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    commit_sha: Mapped[str | None] = mapped_column(String(64), nullable=True)

    runs = relationship("Run", back_populates="batch", foreign_keys="[Run.batch_id]")
