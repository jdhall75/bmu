from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass(slots=True)
class CredentialMaterial:
    """Resolved credential ready to hand to scrapli.

    Only one of ``password`` / ``private_key`` is typically populated.
    """

    username: str
    password: str | None = None
    enable_password: str | None = None
    private_key: str | None = None
    private_key_passphrase: str | None = None


class CredentialResolver(ABC):
    """Resolves a credential record into the actual secret material.

    Implementations must be safe to call from worker processes; they should
    never log the resolved secret.
    """

    @abstractmethod
    def resolve(
        self, *, ref: str | None, encrypted_payload: bytes | None, username: str | None
    ) -> CredentialMaterial: ...
