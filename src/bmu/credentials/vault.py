import os

from bmu.credentials.base import CredentialMaterial, CredentialResolver


class VaultCredentialResolver(CredentialResolver):
    """HashiCorp Vault KV v2 resolver.

    ``ref`` is expected to be ``mount/path`` (e.g. ``secret/bmu/cisco-edge``).
    The secret data should contain the same keys as the local payload schema.
    Configured via env: ``VAULT_ADDR``, ``VAULT_TOKEN`` (or any auth method
    hvac supports).
    """

    def __init__(self, *, addr: str | None = None, token: str | None = None) -> None:
        import hvac

        self._client = hvac.Client(
            url=addr or os.environ.get("VAULT_ADDR"),
            token=token or os.environ.get("VAULT_TOKEN"),
        )

    def resolve(self, *, ref, encrypted_payload, username):
        if not ref or "/" not in ref:
            raise ValueError("vault credential requires ref in 'mount/path' form")
        mount, path = ref.split("/", 1)
        data = self._client.secrets.kv.v2.read_secret_version(
            mount_point=mount, path=path, raise_on_deleted_version=True
        )["data"]["data"]
        return CredentialMaterial(
            username=data.get("username") or username or "",
            password=data.get("password"),
            enable_password=data.get("enable_password"),
            private_key=data.get("private_key"),
            private_key_passphrase=data.get("private_key_passphrase"),
        )
