"""Tests for kiroku.credentials.*

No real Vault/Bitwarden services are required — all external calls are mocked.
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest
from cryptography.fernet import Fernet

from kiroku.credentials.base import CredentialMaterial
from kiroku.credentials.local import LocalCredentialResolver
from kiroku.credentials.registry import _local, _resolver_for, resolve_credential
from kiroku.credentials.vault import VaultCredentialResolver
from kiroku.models.credential import CredentialProvider


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_TEST_KEY = Fernet.generate_key()


def _make_resolver() -> LocalCredentialResolver:
    """Return a LocalCredentialResolver with a known test key, no settings call."""
    resolver = object.__new__(LocalCredentialResolver)
    resolver._fernet = Fernet(_TEST_KEY)
    return resolver


def _encrypt(payload: dict) -> bytes:
    return Fernet(_TEST_KEY).encrypt(json.dumps(payload).encode())


# ---------------------------------------------------------------------------
# LocalCredentialResolver
# ---------------------------------------------------------------------------


class TestLocalCredentialResolver:
    def test_resolve_basic(self):
        resolver = _make_resolver()
        encrypted = _encrypt({"username": "admin", "password": "secret"})
        material = resolver.resolve(ref=None, encrypted_payload=encrypted, username="fallback")
        assert material.username == "admin"
        assert material.password == "secret"

    def test_resolve_falls_back_to_username_kwarg_when_payload_omits_it(self):
        resolver = _make_resolver()
        encrypted = _encrypt({"password": "secret"})
        material = resolver.resolve(ref=None, encrypted_payload=encrypted, username="fallback")
        assert material.username == "fallback"

    def test_resolve_missing_payload_raises(self):
        resolver = _make_resolver()
        with pytest.raises(ValueError, match="missing encrypted_payload"):
            resolver.resolve(ref=None, encrypted_payload=None, username="admin")

    def test_resolve_private_key_and_passphrase(self):
        resolver = _make_resolver()
        encrypted = _encrypt({
            "username": "admin",
            "private_key": "-----BEGIN RSA PRIVATE KEY-----",
            "private_key_passphrase": "passphrase123",
        })
        material = resolver.resolve(ref=None, encrypted_payload=encrypted, username="")
        assert material.private_key == "-----BEGIN RSA PRIVATE KEY-----"
        assert material.private_key_passphrase == "passphrase123"

    def test_resolve_enable_password(self):
        resolver = _make_resolver()
        encrypted = _encrypt({"username": "admin", "password": "pw", "enable_password": "enable"})
        material = resolver.resolve(ref=None, encrypted_payload=encrypted, username="")
        assert material.enable_password == "enable"

    def test_encrypt_produces_bytes(self):
        resolver = _make_resolver()
        result = resolver.encrypt({"username": "u"})
        assert isinstance(result, bytes)

    def test_encrypt_decrypt_roundtrip(self):
        resolver = _make_resolver()
        payload = {"username": "u", "password": "p"}
        encrypted = resolver.encrypt(payload)
        recovered = json.loads(Fernet(_TEST_KEY).decrypt(encrypted))
        assert recovered == payload

    def test_init_uses_settings_fernet_key(self):
        with patch("kiroku.credentials.local.get_settings") as mock_settings:
            mock_settings.return_value.fernet_key = _TEST_KEY
            resolver = LocalCredentialResolver()
        assert resolver._fernet is not None


# ---------------------------------------------------------------------------
# VaultCredentialResolver
# ---------------------------------------------------------------------------


class TestVaultCredentialResolver:
    # hvac is imported inside __init__, so we patch sys.modules to inject a fake.
    def _make_resolver(self, vault_data: dict) -> tuple[VaultCredentialResolver, MagicMock]:
        mock_client = MagicMock()
        mock_client.secrets.kv.v2.read_secret_version.return_value = {
            "data": {"data": vault_data}
        }
        mock_hvac = MagicMock()
        mock_hvac.Client.return_value = mock_client
        with patch.dict("sys.modules", {"hvac": mock_hvac}):
            resolver = VaultCredentialResolver()
        resolver._client = mock_client
        return resolver, mock_client

    def test_resolve_basic(self):
        resolver, _ = self._make_resolver({"username": "vaultuser", "password": "vaultsecret"})
        material = resolver.resolve(ref="secret/kiroku/test", encrypted_payload=None, username="fallback")
        assert material.username == "vaultuser"
        assert material.password == "vaultsecret"

    def test_resolve_uses_username_fallback(self):
        resolver, _ = self._make_resolver({"password": "pw"})
        material = resolver.resolve(ref="secret/kiroku/test", encrypted_payload=None, username="fallback")
        assert material.username == "fallback"

    def test_resolve_splits_ref_into_mount_and_path(self):
        resolver, mock_client = self._make_resolver({"username": "u"})
        resolver.resolve(ref="mymount/some/path", encrypted_payload=None, username="")
        mock_client.secrets.kv.v2.read_secret_version.assert_called_once_with(
            mount_point="mymount", path="some/path", raise_on_deleted_version=True
        )

    def test_resolve_invalid_ref_raises(self):
        resolver, _ = self._make_resolver({})
        with pytest.raises(ValueError, match="mount/path"):
            resolver.resolve(ref="invalid-no-slash", encrypted_payload=None, username="")

    def test_resolve_none_ref_raises(self):
        resolver, _ = self._make_resolver({})
        with pytest.raises(ValueError):
            resolver.resolve(ref=None, encrypted_payload=None, username="")

    def test_resolve_private_key(self):
        resolver, _ = self._make_resolver({
            "username": "u",
            "private_key": "KEY",
            "private_key_passphrase": "pp",
        })
        material = resolver.resolve(ref="m/p", encrypted_payload=None, username="")
        assert material.private_key == "KEY"
        assert material.private_key_passphrase == "pp"

    def test_init_uses_env_vars(self):
        mock_hvac = MagicMock()
        mock_client = MagicMock()
        mock_hvac.Client.return_value = mock_client
        with patch.dict("sys.modules", {"hvac": mock_hvac}):
            VaultCredentialResolver(addr="http://vault:8200", token="mytoken")
        mock_hvac.Client.assert_called_once_with(
            url="http://vault:8200", token="mytoken"
        )


# ---------------------------------------------------------------------------
# registry — _resolver_for and resolve_credential
# ---------------------------------------------------------------------------


class TestRegistry:
    def setup_method(self):
        _local.cache_clear()

    def test_resolver_for_local_returns_local_resolver(self):
        with patch("kiroku.credentials.local.get_settings") as mock_settings:
            mock_settings.return_value.fernet_key = _TEST_KEY
            result = _resolver_for(CredentialProvider.LOCAL)
        assert isinstance(result, LocalCredentialResolver)

    def test_resolver_for_local_is_cached(self):
        with patch("kiroku.credentials.local.get_settings") as mock_settings:
            mock_settings.return_value.fernet_key = _TEST_KEY
            r1 = _resolver_for(CredentialProvider.LOCAL)
            r2 = _resolver_for(CredentialProvider.LOCAL)
        assert r1 is r2

    def test_resolver_for_vault(self):
        mock_hvac = MagicMock()
        mock_hvac.Client.return_value = MagicMock()
        with patch.dict("sys.modules", {"hvac": mock_hvac}):
            result = _resolver_for(CredentialProvider.VAULT)
        assert isinstance(result, VaultCredentialResolver)

    def test_resolver_for_bitwarden_imports_module(self):
        from kiroku.credentials.bitwarden import BitwardenCredentialResolver
        result = _resolver_for(CredentialProvider.BITWARDEN)
        assert isinstance(result, BitwardenCredentialResolver)

    def test_resolver_for_unknown_raises(self):
        with pytest.raises(ValueError, match="unknown credential provider"):
            _resolver_for("not_a_real_provider")

    def test_resolve_credential_delegates_to_resolver(self):
        mock_material = MagicMock(spec=CredentialMaterial)
        mock_resolver = MagicMock()
        mock_resolver.resolve.return_value = mock_material

        cred = MagicMock()
        cred.provider = CredentialProvider.LOCAL
        cred.ref = "myref"
        cred.encrypted_payload = b"enc"
        cred.username = "admin"

        with patch("kiroku.credentials.registry._resolver_for", return_value=mock_resolver):
            result = resolve_credential(cred)

        assert result is mock_material
        mock_resolver.resolve.assert_called_once_with(
            ref="myref", encrypted_payload=b"enc", username="admin"
        )
