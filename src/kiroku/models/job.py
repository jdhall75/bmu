import enum

import sqlalchemy as sa
from sqlalchemy import Enum as SAEnum, ForeignKey, String, Table, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from kiroku.db.base import Base, TimestampMixin


class JobKind(str, enum.Enum):
    BACKUP = "backup"
    COLLECT = "collect"
    CVE_SCAN = "cve_scan"


job_device_groups = Table(
    "job_device_groups",
    Base.metadata,
    sa.Column(
        "job_id",
        sa.Integer(),
        sa.ForeignKey("jobs.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    sa.Column(
        "device_group_id",
        sa.Integer(),
        sa.ForeignKey("device_groups.id", ondelete="CASCADE"),
        primary_key=True,
    ),
)

job_devices = Table(
    "job_devices",
    Base.metadata,
    sa.Column(
        "job_id",
        sa.Integer(),
        sa.ForeignKey("jobs.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    sa.Column(
        "device_id",
        sa.Integer(),
        sa.ForeignKey("devices.id", ondelete="CASCADE"),
        primary_key=True,
    ),
)


class Job(Base, TimestampMixin):
    __tablename__ = "jobs"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    kind: Mapped[JobKind] = mapped_column(
        SAEnum(
            JobKind,
            name="job_kind",
            values_callable=lambda e: [m.value for m in e],
            create_type=False,
        ),
        nullable=False,
    )
    commands: Mapped[str | None] = mapped_column(Text, nullable=True)
    rpc: Mapped[str | None] = mapped_column(Text, nullable=True)
    parser_template_id: Mapped[int | None] = mapped_column(
        ForeignKey("parser_templates.id", ondelete="SET NULL"), nullable=True
    )
    parser_template = relationship("ParserTemplate")
    cve_vendor: Mapped[str | None] = mapped_column(String(64), nullable=True)
    cve_product: Mapped[str | None] = mapped_column(String(64), nullable=True)
    show_on_device: Mapped[bool] = mapped_column(
        sa.Boolean, nullable=False, default=False
    )

    device_groups = relationship(
        "DeviceGroup", secondary=job_device_groups, backref="jobs"
    )
    devices = relationship("Device", secondary=job_devices, backref="jobs")
