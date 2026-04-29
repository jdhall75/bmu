from bmu.credentials.base import CredentialMaterial, CredentialResolver


class BitwardenCredentialResolver(CredentialResolver):
    """Stub for Bitwarden Secrets Manager. Not wired in MVP."""

    def resolve(self, *, ref, encrypted_payload, username):  # pragma: no cover
        raise NotImplementedError("Bitwarden provider not yet implemented")
