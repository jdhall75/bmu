import enum

from sqlalchemy import Enum as SAEnum
from sqlalchemy import ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from bmu.db.base import Base, TimestampMixin


class ProfileKind(str, enum.Enum):
    CLI = "cli"
    NETCONF = "netconf"


class TransportProtocol(str, enum.Enum):
    SSH = "ssh"
    TELNET = "telnet"
    NETCONF = "netconf"


class Profile(Base, TimestampMixin):
    """How to talk to a device.

    A profile is one of two flavors:

    * CLI - references a scrapli platform (e.g. ``cisco_iosxe``) or
      ``generic`` for unsupported gear, in which case ``prompt_pattern``,
      ``pre_commands`` and ``disable_paging_command`` carry the overrides.
    * NETCONF - carries an RPC payload to send and an optional XSLT parser
      template to transform the response.
    """

    __tablename__ = "profiles"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    kind: Mapped[ProfileKind] = mapped_column(
        SAEnum(
            ProfileKind,
            name="profile_kind",
            values_callable=lambda e: [m.value for m in e],
        ),
        nullable=False,
    )

    # ---- CLI fields ------------------------------------------------------
    # scrapli platform name; "generic" means use GenericDriver with overrides.
    platform: Mapped[str | None] = mapped_column(String(64), nullable=True)
    transport: Mapped[TransportProtocol | None] = mapped_column(
        SAEnum(
            TransportProtocol,
            name="transport_protocol",
            values_callable=lambda e: [m.value for m in e],
        ),
        nullable=True,
    )
    port: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # Used when platform == "generic":
    prompt_pattern: Mapped[str | None] = mapped_column(String(256), nullable=True)
    # Newline-separated list of commands run before the backup command,
    # e.g. ``enable`` on a Cisco device.
    pre_commands: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Command to disable paging (e.g. ``terminal length 0``); optional, used
    # only when scrapli's platform support doesn't already handle it.
    disable_paging_command: Mapped[str | None] = mapped_column(String(256), nullable=True)
    # The actual command(s) to collect; newline-separated. For backups this
    # is typically ``show running-config``; for data collection it can be
    # any list of show commands.
    commands: Mapped[str | None] = mapped_column(Text, nullable=True)

    # ---- NETCONF fields --------------------------------------------------
    # Free-text manufacturer hint for the operator (informational).
    manufacturer: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # Raw RPC XML to send.
    rpc: Mapped[str | None] = mapped_column(Text, nullable=True)

    # ---- Optional parser -------------------------------------------------
    parser_template_id: Mapped[int | None] = mapped_column(
        ForeignKey("parser_templates.id", ondelete="SET NULL"), nullable=True
    )
    parser_template = relationship("ParserTemplate")

    # ---- CVE scanning ----------------------------------------------------
    # CPE vendor and product hints used to query the CVE API after the
    # parser template extracts a version string from the device output.
    # e.g. cve_vendor="cisco", cve_product="ios_xe"
    cve_vendor: Mapped[str | None] = mapped_column(String(64), nullable=True)
    cve_product: Mapped[str | None] = mapped_column(String(64), nullable=True)
