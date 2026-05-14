from __future__ import annotations

import enum
from datetime import datetime

import sqlalchemy as sa
from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Table, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from kiroku.db.base import Base, TimestampMixin


class ComplianceSeverity(str, enum.Enum):
    CRITICAL = "critical"
    MAJOR = "major"
    MINOR = "minor"
    INFO = "info"


class ComplianceStatus(str, enum.Enum):
    PASS = "pass"
    FAIL = "fail"
    ERROR = "error"
    SKIP = "skip"


compliance_policy_groups = Table(
    "compliance_policy_groups",
    Base.metadata,
    sa.Column("policy_id", Integer, ForeignKey("compliance_policies.id", ondelete="CASCADE"), primary_key=True),
    sa.Column("device_group_id", Integer, ForeignKey("device_groups.id", ondelete="CASCADE"), primary_key=True),
)

compliance_policy_devices = Table(
    "compliance_policy_devices",
    Base.metadata,
    sa.Column("policy_id", Integer, ForeignKey("compliance_policies.id", ondelete="CASCADE"), primary_key=True),
    sa.Column("device_id", Integer, ForeignKey("devices.id", ondelete="CASCADE"), primary_key=True),
)


class CompliancePolicy(Base, TimestampMixin):
    __tablename__ = "compliance_policies"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    parser_type: Mapped[str] = mapped_column(String(16), nullable=False)  # textfsm | ttp | parse
    parser_body: Mapped[str] = mapped_column(Text, nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    auto_evaluate: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    checks: Mapped[list[ComplianceCheck]] = relationship(
        "ComplianceCheck", back_populates="policy",
        cascade="all, delete-orphan", order_by="ComplianceCheck.sort_order",
    )
    results: Mapped[list[ComplianceResult]] = relationship(
        "ComplianceResult", back_populates="policy", cascade="all, delete-orphan",
    )
    device_groups = relationship("DeviceGroup", secondary=compliance_policy_groups)
    devices = relationship("Device", secondary=compliance_policy_devices)


class ComplianceCheck(Base):
    __tablename__ = "compliance_checks"

    id: Mapped[int] = mapped_column(primary_key=True)
    policy_id: Mapped[int] = mapped_column(ForeignKey("compliance_policies.id", ondelete="CASCADE"), nullable=False)
    policy: Mapped[CompliancePolicy] = relationship("CompliancePolicy", back_populates="checks")

    name: Mapped[str] = mapped_column(String(128), nullable=False)
    field: Mapped[str] = mapped_column(String(64), nullable=False)
    operator: Mapped[str] = mapped_column(String(16), nullable=False)  # eq|ne|contains|not_contains|regex|gt|lt|ge|le|exists|not_exists
    expected: Mapped[str | None] = mapped_column(Text, nullable=True)
    mode: Mapped[str] = mapped_column(String(8), nullable=False, default="any")  # any|all|none
    severity: Mapped[str] = mapped_column(String(8), nullable=False, default="major")
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class ComplianceResult(Base):
    __tablename__ = "compliance_results"
    __table_args__ = (sa.UniqueConstraint("policy_id", "device_id", name="uq_compliance_results_policy_device"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    policy_id: Mapped[int] = mapped_column(ForeignKey("compliance_policies.id", ondelete="CASCADE"), nullable=False)
    policy: Mapped[CompliancePolicy] = relationship("CompliancePolicy", back_populates="results")
    device_id: Mapped[int] = mapped_column(ForeignKey("devices.id", ondelete="CASCADE"), nullable=False)
    device = relationship("Device")

    evaluated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[str] = mapped_column(String(8), nullable=False)  # ComplianceStatus value
    detail: Mapped[list | None] = mapped_column(JSONB, nullable=True)
