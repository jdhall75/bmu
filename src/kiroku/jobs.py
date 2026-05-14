"""Job spec / result schemas exchanged through Redis streams.

The contents are JSON-serialized into the stream entry's ``data`` field.

Credentials are resolved by the dispatcher and embedded in the spec so that
workers need no database connection.  The resolved secrets travel inside the
Redis stream — secure Redis with TLS (rediss://) and AUTH.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class CredentialRef(BaseModel):
    provider: Literal["local", "vault", "bitwarden"]
    credential_id: int
    # Optional, redundant pointer (helps Vault/Bitwarden resolvers).
    ref: str | None = None


class EmbeddedCredential(BaseModel):
    """Resolved credential material embedded in the JobSpec.

    Populated by the dispatcher so the worker requires no database access.
    Secrets are serialised into the Redis stream — protect the stream with
    TLS (``rediss://``) and Redis AUTH.
    """

    username: str
    password: str | None = None
    enable_password: str | None = None
    private_key: str | None = None
    private_key_passphrase: str | None = None


class JobSpec(BaseModel):
    """A unit of work for one device."""

    run_id: int
    schedule_id: int | None = None
    device_id: int
    device_name: str
    hostname: str
    port: int | None = None

    kind: Literal["backup", "collect", "cve_scan"]

    job_id: int
    driver_kind: Literal["cli", "netconf"]
    # CLI fields (None for netconf):
    platform: str | None = None
    # Operator-defined platform YAML; when set, written to a tempfile and
    # passed to Cli(definition_file_or_name=...) instead of platform name.
    custom_platform_yaml: str | None = None
    transport: str | None = None
    commands: list[str] = Field(default_factory=list)
    # NETCONF fields:
    rpc: str | None = None

    parser_template_id: int | None = None
    parser_type: Literal["textfsm", "ttp", "xslt"] | None = None
    parser_body: str | None = None

    # CVE scan fields (only populated for kind="cve_scan"):
    cve_vendor: str | None = None
    cve_product: str | None = None

    # Per-device timeout overrides (None → use worker global defaults).
    connect_timeout: int | None = None
    command_timeout: int | None = None

    # Worker pool this job is routed to.  None = default pool (kiroku:jobs).
    # Set by the dispatcher based on device.worker_pool > group.worker_pool > None.
    worker_pool: str | None = None

    credential: CredentialRef
    # Resolved material embedded at dispatch time — workers use this directly.
    credential_material: EmbeddedCredential | None = None


class CommandResult(BaseModel):
    command: str
    output: str
    elapsed_ms: int
    failed: bool = False


class JobResult(BaseModel):
    run_id: int
    device_id: int
    device_name: str
    kind: Literal["backup", "collect", "cve_scan"]

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
    # Set when parsing was attempted but failed; None means not attempted or succeeded.
    parse_error: str | None = None
    parser_template_id: int | None = None
    job_id: int | None = None

    # CVE scan results (only populated for kind="cve_scan").
    cve_entries: list[dict] = Field(default_factory=list)
    # CPE string used for the query (first version row; empty if no version found).
    cpe: str | None = None
