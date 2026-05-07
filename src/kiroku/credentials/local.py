import json

from cryptography.fernet import Fernet

from kiroku.config import get_settings
from kiroku.credentials.base import CredentialMaterial, CredentialResolver


class LocalCredentialResolver(CredentialResolver):
    """Decrypts a Fernet-encrypted JSON blob stored on the credential row.

    Payload schema::

        {
          "username": "admin",
          "password": "...",          # optional
          "enable_password": "...",   # optional
          "private_key": "...",       # optional, PEM string
          "private_key_passphrase": "..."  # optional
        }
    """

    def __init__(self) -> None:
        self._fernet = Fernet(get_settings().fernet_key)

    def encrypt(self, payload: dict) -> bytes:
        return self._fernet.encrypt(json.dumps(payload).encode("utf-8"))

    def resolve(self, *, ref, encrypted_payload, username):
        if not encrypted_payload:
            raise ValueError("local credential is missing encrypted_payload")
        data = json.loads(self._fernet.decrypt(encrypted_payload).decode("utf-8"))
        return CredentialMaterial(
            username=data.get("username") or username or "",
            password=data.get("password"),
            enable_password=data.get("enable_password"),
            private_key=data.get("private_key"),
            private_key_passphrase=data.get("private_key_passphrase"),
        )
