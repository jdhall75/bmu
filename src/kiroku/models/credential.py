import enum

from sqlalchemy import Enum as SAEnum
from sqlalchemy import LargeBinary, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from kiroku.db.base import Base, TimestampMixin


class CredentialProvider(str, enum.Enum):
    LOCAL = "local"
    VAULT = "vault"
    BITWARDEN = "bitwarden"


class Credential(Base, TimestampMixin):
    __tablename__ = "credentials"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    provider: Mapped[CredentialProvider] = mapped_column(
        SAEnum(
            CredentialProvider,
            name="credential_provider",
            values_callable=lambda e: [m.value for m in e],
        ),
        nullable=False,
    )
    # For provider=local: opaque encrypted blob.
    # For provider=vault/bitwarden: pointer (path / id) is stored in `ref`.
    encrypted_payload: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    ref: Mapped[str | None] = mapped_column(String(512), nullable=True)
    # Optional username (often public; helps the UI without resolving the secret).
    username: Mapped[str | None] = mapped_column(String(128), nullable=True)
