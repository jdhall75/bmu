import enum
from datetime import datetime

from sqlalchemy import DateTime, JSON
from sqlalchemy import Enum as SAEnum
from sqlalchemy import ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from kiroku.db.base import Base, TimestampMixin


class RunStatus(str, enum.Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    TIMEOUT = "timeout"
    CANCELLED = "cancelled"


class Run(Base, TimestampMixin):
    """One execution of a job spec against one device."""

    __tablename__ = "runs"

    id: Mapped[int] = mapped_column(primary_key=True)

    schedule_id: Mapped[int | None] = mapped_column(
        ForeignKey("schedules.id", ondelete="SET NULL"), nullable=True
    )
    batch_id: Mapped[int | None] = mapped_column(
        ForeignKey("run_batches.id", ondelete="SET NULL"), nullable=True
    )
    batch = relationship("RunBatch", back_populates="runs")

    device_id: Mapped[int] = mapped_column(
        ForeignKey("devices.id", ondelete="CASCADE"), nullable=False
    )
    device = relationship("Device")

    kind: Mapped[str] = mapped_column(String(16), nullable=False)  # JobKind value
    status: Mapped[RunStatus] = mapped_column(
        SAEnum(
            RunStatus,
            name="run_status",
            values_callable=lambda e: [m.value for m in e],
        ),
        default=RunStatus.PENDING,
        nullable=False,
    )

    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # For backup runs: git commit sha that recorded the config (if changed).
    commit_sha: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # SHA-256 of the captured payload; lets us short-circuit no-change runs.
    payload_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    bytes_captured: Mapped[int | None] = mapped_column(Integer, nullable=True)

    error: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Structured output from TTP/TextFSM/XSLT parsers for collect/NETCONF runs.
    parsed_data: Mapped[list | dict | None] = mapped_column(JSON, nullable=True)
    # Set when parsing was attempted but failed.
    parse_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Which parser template produced parsed_data (kept even if the template is later edited).
    parser_template_id: Mapped[int | None] = mapped_column(
        ForeignKey("parser_templates.id", ondelete="SET NULL"), nullable=True
    )
    parser_template = relationship("ParserTemplate")
    # Which job produced this run.
    job_id: Mapped[int | None] = mapped_column(
        ForeignKey("jobs.id", ondelete="SET NULL"), nullable=True
    )
    job = relationship("Job")
