from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from bmu.db.base import Base, TimestampMixin


class CveScan(Base, TimestampMixin):
    __tablename__ = "cve_scans"

    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[int | None] = mapped_column(
        ForeignKey("runs.id", ondelete="SET NULL"), nullable=True
    )
    device_id: Mapped[int] = mapped_column(
        ForeignKey("devices.id", ondelete="CASCADE"), nullable=False
    )
    device = relationship("Device")

    cpe: Mapped[str] = mapped_column(String(256), nullable=False)
    version_found: Mapped[str | None] = mapped_column(String(128), nullable=True)
    raw_version: Mapped[str | None] = mapped_column(String(128), nullable=True)
    scanned_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    results: Mapped[list["CveResult"]] = relationship(
        "CveResult", back_populates="scan", cascade="all, delete-orphan"
    )


class CveResult(Base):
    __tablename__ = "cve_results"

    id: Mapped[int] = mapped_column(primary_key=True)
    scan_id: Mapped[int] = mapped_column(
        ForeignKey("cve_scans.id", ondelete="CASCADE"), nullable=False
    )
    scan: Mapped[CveScan] = relationship("CveScan", back_populates="results")

    cve_id: Mapped[str] = mapped_column(String(32), nullable=False)
    cvss_v3_score: Mapped[float | None] = mapped_column(Numeric(4, 1), nullable=True)
    severity: Mapped[str | None] = mapped_column(String(16), nullable=True)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    url: Mapped[str | None] = mapped_column(String(512), nullable=True)
