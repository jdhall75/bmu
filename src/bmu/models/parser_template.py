import enum

from sqlalchemy import Enum as SAEnum
from sqlalchemy import String, Text
from sqlalchemy.orm import Mapped, mapped_column

from bmu.db.base import Base, TimestampMixin


class ParserType(str, enum.Enum):
    TEXTFSM = "textfsm"
    TTP = "ttp"
    XSLT = "xslt"


class ParserTemplate(Base, TimestampMixin):
    __tablename__ = "parser_templates"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    type: Mapped[ParserType] = mapped_column(
        SAEnum(ParserType, name="parser_type"), nullable=False
    )
    body: Mapped[str] = mapped_column(Text, nullable=False)
