"""Job spec / result schemas exchanged through Redis streams.

The contents are JSON-serialized into the stream entry's ``data`` field.
Workers must never receive resolved secrets here; only references.
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class CredentialRef(BaseModel):
    provider: Literal["local", "vault", "bitwarden"]
    credential_id: int
    # Optional, redundant pointer (helps Vault/Bitwarden resolvers).
    ref: str | None = None


class JobSpec(BaseModel):
    """A unit of work for one device."""

    run_id: int
    schedule_id: int | None = None
    device_id: int
    device_name: str
    hostname: str
    port: int | None = None

    kind: Literal["backup", "collect"]

    profile_id: int
    profile_kind: Literal["cli", "netconf"]
    # CLI fields (None for netconf):
    platform: str | None = None
    transport: str | None = None
    prompt_pattern: str | None = None
    pre_commands: list[str] = Field(default_factory=list)
    disable_paging_command: str | None = None
    commands: list[str] = Field(default_factory=list)
    # NETCONF fields:
    rpc: str | None = None

    parser_template_id: int | None = None
    parser_type: Literal["textfsm", "ttp", "xslt"] | None = None
    parser_body: str | None = None

    credential: CredentialRef


class CommandResult(BaseModel):
    command: str
    output: str
    elapsed_ms: int
    failed: bool = False


class JobResult(BaseModel):
    run_id: int
    device_id: int
    device_name: str
    kind: Literal["backup", "collect"]

    success: bool
    error: str | None = None

    started_at: str  # ISO timestamp
    finished_at: str

    # For backup runs: the concatenated config to record.
    config_text: str | None = None

    # For collect runs: list of parser-flattened command results.
    command_results: list[CommandResult] = Field(default_factory=list)

    # Optional structured rows (from textfsm/ttp/xslt). Stored alongside the run
    # for inspection in the UI.
    parsed: list[dict] | dict | None = None
