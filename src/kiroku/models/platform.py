from sqlalchemy import String, Text
from sqlalchemy.orm import Mapped, mapped_column

from kiroku.db.base import Base, TimestampMixin


class Platform(Base, TimestampMixin):
    """Operator-defined scrapli platform YAML definition.

    The yaml_body is written to a temp file at run time and passed to
    scrapli's Cli(definition_file_or_name=...).
    """

    __tablename__ = "platforms"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    yaml_body: Mapped[str] = mapped_column(Text, nullable=False)
