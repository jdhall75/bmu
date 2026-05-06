"""Shared fixtures and helpers for worker tests."""
from unittest.mock import MagicMock

import pytest

from bmu.credentials.base import CredentialMaterial
from bmu.jobs import CredentialRef, JobSpec


def make_cred(**kwargs) -> CredentialMaterial:
    defaults = dict(username="admin", password="secret", enable_password=None, private_key=None)
    return CredentialMaterial(**{**defaults, **kwargs})


def make_spec(**kwargs) -> JobSpec:
    defaults = dict(
        run_id=1,
        device_id=10,
        device_name="test-device",
        hostname="192.168.1.1",
        port=22,
        kind="backup",
        profile_id=1,
        profile_kind="cli",
        platform="cisco_iosxe",
        transport="ssh",
        prompt_pattern=None,
        pre_commands=[],
        disable_paging_command=None,
        commands=["show running-config"],
        credential=CredentialRef(provider="local", credential_id=1),
    )
    return JobSpec(**{**defaults, **kwargs})


def mock_response(result="output", failed=False) -> MagicMock:
    r = MagicMock()
    r.result = result
    r.failed = failed
    return r


def make_driver(*responses) -> MagicMock:
    """Return a mock scrapli driver. Pass mock_response() objects for send_command."""
    driver = MagicMock()
    if responses:
        driver.send_command.side_effect = list(responses)
    else:
        driver.send_command.return_value = mock_response()
    return driver


@pytest.fixture
def mock_settings():
    s = MagicMock()
    s.worker_connect_timeout = 30
    s.worker_command_timeout = 60
    return s
