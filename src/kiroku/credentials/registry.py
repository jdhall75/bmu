from functools import lru_cache

from kiroku.credentials.base import CredentialMaterial, CredentialResolver
from kiroku.credentials.local import LocalCredentialResolver
from kiroku.models.credential import Credential, CredentialProvider


@lru_cache(maxsize=1)
def _local() -> CredentialResolver:
    return LocalCredentialResolver()


def _resolver_for(provider: CredentialProvider) -> CredentialResolver:
    if provider is CredentialProvider.LOCAL:
        return _local()
    if provider is CredentialProvider.VAULT:
        from kiroku.credentials.vault import VaultCredentialResolver

        return VaultCredentialResolver()
    if provider is CredentialProvider.BITWARDEN:
        from kiroku.credentials.bitwarden import BitwardenCredentialResolver

        return BitwardenCredentialResolver()
    raise ValueError(f"unknown credential provider: {provider!r}")


def resolve_credential(cred: Credential) -> CredentialMaterial:
    return _resolver_for(cred.provider).resolve(
        ref=cred.ref,
        encrypted_payload=cred.encrypted_payload,
        username=cred.username,
    )
