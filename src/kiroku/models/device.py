import enum
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from kiroku.db.base import Base, TimestampMixin
from kiroku.models.membership import device_group_memberships


class DriverKind(str, enum.Enum):
    CLI = "cli"
    NETCONF = "netconf"


class TransportProtocol(str, enum.Enum):
    SSH = "ssh"
    TELNET = "telnet"
    NETCONF = "netconf"


class Device(Base, TimestampMixin):
    __tablename__ = "devices"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    hostname: Mapped[str] = mapped_column(String(255), nullable=False)
    port: Mapped[int | None] = mapped_column(Integer, nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    groups: Mapped[list["DeviceGroup"]] = relationship(
        "DeviceGroup", secondary=device_group_memberships, back_populates="devices"
    )

    # Driver / connection configuration
    platform: Mapped[str | None] = mapped_column(String(64), nullable=True)
    custom_platform_id: Mapped[int | None] = mapped_column(
        ForeignKey("platforms.id", ondelete="SET NULL"), nullable=True
    )
    custom_platform = relationship("Platform")
    transport: Mapped[TransportProtocol | None] = mapped_column(
        SAEnum(
            TransportProtocol,
            name="transport_protocol",
            values_callable=lambda e: [m.value for m in e],
            create_constraint=False,
            create_type=False,
        ),
        nullable=True,
    )
    driver_kind: Mapped[DriverKind | None] = mapped_column(
        SAEnum(
            DriverKind,
            values_callable=lambda e: [m.value for m in e],
            native_enum=False,
        ),
        nullable=True,
    )

    # Per-device timeout overrides; None means use the global config defaults.
    connect_timeout: Mapped[int | None] = mapped_column(Integer, nullable=True)
    command_timeout: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Per-device credential override; falls back to the group's default.
    credential_id: Mapped[int | None] = mapped_column(
        ForeignKey("credentials.id", ondelete="SET NULL"), nullable=True
    )
    credential = relationship("Credential")

    enabled: Mapped[bool] = mapped_column(default=True, nullable=False)

    latest_backup_path: Mapped[str | None] = mapped_column(String(512), nullable=True)
    latest_backup_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
