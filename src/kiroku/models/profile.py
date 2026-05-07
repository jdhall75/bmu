import enum

from sqlalchemy import Enum as SAEnum
from sqlalchemy import ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from kiroku.db.base import Base, TimestampMixin


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

    * CLI - references a built-in scrapli platform (e.g. ``cisco_iosxe``)
      or an operator-defined custom Platform whose YAML is passed to
      ``Cli(definition_file_or_name=…)`` at run time.
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
    # Built-in scrapli platform name (e.g. "cisco_iosxe"). Mutually
    # exclusive with custom_platform_id below.
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
    # The actual command(s) to collect; newline-separated. For backups this
    # is typically ``show running-config``; for data collection it can be
    # any list of show commands.
    commands: Mapped[str | None] = mapped_column(Text, nullable=True)

    # ---- NETCONF fields --------------------------------------------------
    # Free-text manufacturer hint for the operator (informational).
    manufacturer: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # Raw RPC XML to send.
    rpc: Mapped[str | None] = mapped_column(Text, nullable=True)

    # ---- Custom platform (operator-defined scrapli YAML) -----------------
    # Mutually exclusive with the built-in platform string above.
    # When set, the yaml_body is written to a tempfile at run time.
    custom_platform_id: Mapped[int | None] = mapped_column(
        ForeignKey("platforms.id", ondelete="SET NULL"), nullable=True
    )
    custom_platform = relationship("Platform")

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
