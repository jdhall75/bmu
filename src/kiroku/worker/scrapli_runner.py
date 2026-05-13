"""Run a JobSpec against a real device using scrapli2 (sync).

scrapli2 unifies CLI and NETCONF into a single package. The transport is
chosen by the type of TransportOptions passed:
  - TransportBinOptions  → bin/OpenSSH (default for SSH)
  - TransportTelnetOptions → telnet

Platform definitions are YAML files. Built-in definitions cover the core
platforms (cisco_iosxe, cisco_iosxr, etc.). Operator-defined platforms are
stored in the database and passed via JobSpec.custom_platform_yaml; the
worker writes the YAML to a temp file, passes the path to
Cli(definition_file_or_name=…), then deletes it after open().

Enable passwords are passed via AuthOptions.lookups; they take effect when
a platform definition references __lookup::enable in its instructions.
"""

from __future__ import annotations

import contextlib
import os
import tempfile
import time
import traceback
from datetime import datetime, timezone

from scrapli import (
    AuthOptions,
    Cli,
    LookupKeyValue,
    Netconf,
    SessionOptions,
    TransportBinOptions,
    TransportTelnetOptions,
)

from kiroku.config import get_settings
from kiroku.credentials.base import CredentialMaterial
from kiroku.jobs import CommandResult, JobResult, JobSpec
from kiroku.logging import get_logger
from kiroku.parsers import parse

log = get_logger(__name__)


def _now_iso() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


def _build_cli_driver(
    spec: JobSpec, cred: CredentialMaterial
) -> tuple[Cli, str | None]:
    """Build a Cli driver for the given spec.

    Returns (driver, temp_definition_path). temp_definition_path is non-None
    only for the generic platform; callers must delete it after driver.open().
    """
    settings = get_settings()
    connect_timeout = spec.connect_timeout or settings.worker_connect_timeout
    command_timeout = spec.command_timeout or settings.worker_command_timeout

    lookups = (
        [LookupKeyValue(key="enable", value=cred.enable_password)]
        if cred.enable_password
        else None
    )
    auth = AuthOptions(
        username=cred.username,
        password=cred.password or "",
        private_key_path=cred.private_key or None,
        private_key_passphrase=cred.private_key_passphrase or None,
        lookups=lookups,
    )
    session = SessionOptions(operation_timeout_s=command_timeout)

    if spec.transport == "telnet":
        transport_opts: TransportBinOptions | TransportTelnetOptions = (
            TransportTelnetOptions()
        )
        default_port = 23
    else:
        # Pass ConnectTimeout to the SSH binary via extra_open_args.
        transport_opts = TransportBinOptions(
            enable_strict_key=False,
            extra_open_args=["-o", f"ConnectTimeout={connect_timeout}"],
        )
        default_port = 22

    temp_path: str | None = None

    platform_name = (spec.platform or "").lower()
    if spec.custom_platform_yaml:
        fd, temp_path = tempfile.mkstemp(suffix=".yaml", prefix="kiroku_def_")
        with os.fdopen(fd, "w") as fh:
            fh.write(spec.custom_platform_yaml)
        definition: str | None = temp_path
    elif platform_name:
        definition = platform_name
    else:
        raise ValueError("device has no platform or custom_platform_yaml configured")

    driver = Cli(
        host=spec.hostname,
        port=spec.port or default_port,
        definition_file_or_name=definition,
        auth_options=auth,
        session_options=session,
        transport_options=transport_opts,
    )
    return driver, temp_path


def _run_cli(spec: JobSpec, cred: CredentialMaterial) -> JobResult:
    started = _now_iso()
    driver, temp_path = _build_cli_driver(spec, cred)
    config_chunks: list[str] = []
    cmd_results: list[CommandResult] = []
    error: str | None = None
    try:
        driver.open()
        with contextlib.suppress(OSError):
            if temp_path:
                os.unlink(temp_path)
                temp_path = None
        for cmd in spec.commands:
            t0 = time.perf_counter()
            resp = driver.send_input(input_=cmd)
            elapsed_ms = int((time.perf_counter() - t0) * 1000)
            cmd_results.append(
                CommandResult(
                    command=cmd,
                    output=resp.result,
                    elapsed_ms=elapsed_ms,
                    failed=resp.failed,
                )
            )
            if spec.kind == "backup":
                config_chunks.append(resp.result)
        driver.close()
    except Exception as exc:
        error = f"{type(exc).__name__}: {exc}\n\n{traceback.format_exc()}"
        log.error("CLI run failed", device=spec.device_name, error=error)
        # driver.close() is intentionally skipped: calling close() on a session
        # that raised (e.g. OperationException: TimeoutExceeded) blocks on the
        # underlying socket. The OS reclaims the connection on its own.
    finally:
        with contextlib.suppress(OSError):
            if temp_path:
                os.unlink(temp_path)

    parsed = None
    parse_error: str | None = None
    if spec.kind == "collect" and spec.parser_type and cmd_results:
        joined = "\n".join(c.output for c in cmd_results)
        try:
            parsed = parse(spec.parser_type, spec.parser_body, joined)
            log.info(
                "collect parse complete",
                device=spec.device_name,
                parser=spec.parser_type,
                result_type=type(parsed).__name__,
                rows=len(parsed) if isinstance(parsed, list) else None,
            )
        except Exception as exc:
            parse_error = f"{type(exc).__name__}: {exc}\n\n{traceback.format_exc()}"
            log.error(
                "parser failed",
                device=spec.device_name,
                parser=spec.parser_type,
                error=str(exc),
                exc_info=True,
            )
    elif spec.kind == "collect" and not spec.parser_type:
        log.debug("collect: no parser template attached", device=spec.device_name)

    return JobResult(
        run_id=spec.run_id,
        device_id=spec.device_id,
        device_name=spec.device_name,
        kind=spec.kind,
        success=error is None and not any(c.failed for c in cmd_results),
        error=error,
        started_at=started,
        finished_at=_now_iso(),
        config_text="\n".join(config_chunks) if config_chunks else None,
        command_results=cmd_results,
        parsed=parsed,
        parse_error=parse_error,
        parser_template_id=spec.parser_template_id,
        job_id=spec.job_id,
    )


def _run_netconf(spec: JobSpec, cred: CredentialMaterial) -> JobResult:
    started = _now_iso()
    error: str | None = None
    raw_xml: str | None = None
    parsed = None

    try:
        settings = get_settings()
        connect_timeout = spec.connect_timeout or settings.worker_connect_timeout
        command_timeout = spec.command_timeout or settings.worker_command_timeout
        driver = Netconf(
            host=spec.hostname,
            port=spec.port or 830,
            auth_options=AuthOptions(
                username=cred.username,
                password=cred.password or "",
            ),
            session_options=SessionOptions(operation_timeout_s=command_timeout),
            transport_options=TransportBinOptions(
                enable_strict_key=False,
                extra_open_args=["-o", f"ConnectTimeout={connect_timeout}"],
            ),
        )
        driver.open()
        if not spec.rpc:
            raise ValueError("netconf profile is missing rpc")
        resp = driver.raw_rpc(rpc=spec.rpc)
        raw_xml = resp.result
        driver.close()
    except Exception as exc:
        error = f"{type(exc).__name__}: {exc}\n\n{traceback.format_exc()}"
        log.error("NETCONF run failed", device=spec.device_name, error=error)
        # driver.close() intentionally skipped on exception — same reason as _run_cli.

    if raw_xml and spec.parser_type:
        try:
            parsed = parse(spec.parser_type, spec.parser_body, raw_xml)
        except Exception as exc:
            log.error("parser failed", device=spec.device_name, error=str(exc))

    return JobResult(
        run_id=spec.run_id,
        device_id=spec.device_id,
        device_name=spec.device_name,
        kind=spec.kind,
        success=error is None,
        error=error,
        started_at=started,
        finished_at=_now_iso(),
        config_text=raw_xml if spec.kind == "backup" else None,
        command_results=[],
        parsed=parsed,
        parser_template_id=spec.parser_template_id,
        job_id=spec.job_id,
    )


def _run_cve_scan(spec: JobSpec, cred: CredentialMaterial) -> JobResult:
    """Run commands, parse version output, then query the CVE API."""
    started = _now_iso()
    driver, temp_path = _build_cli_driver(spec, cred)
    cmd_results: list[CommandResult] = []
    error: str | None = None
    try:
        driver.open()
        with contextlib.suppress(OSError):
            if temp_path:
                os.unlink(temp_path)
                temp_path = None
        for cmd in spec.commands:
            t0 = time.perf_counter()
            resp = driver.send_input(input_=cmd)
            elapsed_ms = int((time.perf_counter() - t0) * 1000)
            cmd_results.append(
                CommandResult(
                    command=cmd,
                    output=resp.result,
                    elapsed_ms=elapsed_ms,
                    failed=resp.failed,
                )
            )
        driver.close()
    except Exception as exc:
        error = f"{type(exc).__name__}: {exc}\n\n{traceback.format_exc()}"
        log.error("CVE scan CLI run failed", device=spec.device_name, error=error)
        # driver.close() intentionally skipped on exception — same reason as _run_cli.
    finally:
        with contextlib.suppress(OSError):
            if temp_path:
                os.unlink(temp_path)

    parsed = None
    if spec.parser_type and cmd_results:
        joined = "\n".join(c.output for c in cmd_results)
        try:
            parsed = parse(spec.parser_type, spec.parser_body, joined)
        except Exception as exc:
            log.error("parser failed", device=spec.device_name, error=str(exc))

    cve_entries: list[dict] = []
    first_cpe: str | None = None
    if error is None and parsed and spec.cve_vendor and spec.cve_product:
        from kiroku.cve import query_cpe

        rows = parsed if isinstance(parsed, list) else [parsed]
        for row in rows:
            version = row.get("version") if isinstance(row, dict) else None
            if not version:
                continue
            cpe = (
                f"cpe:2.3:o:{spec.cve_vendor}:{spec.cve_product}"
                f":{version}:*:*:*:*:*:*:*"
            )
            if first_cpe is None:
                first_cpe = cpe
            try:
                cve_entries.extend(query_cpe(cpe))
            except Exception as exc:
                log.error("CVE query failed", cpe=cpe, error=str(exc))

    return JobResult(
        run_id=spec.run_id,
        device_id=spec.device_id,
        device_name=spec.device_name,
        kind=spec.kind,
        success=error is None and not any(c.failed for c in cmd_results),
        error=error,
        started_at=started,
        finished_at=_now_iso(),
        command_results=cmd_results,
        parsed=parsed,
        cve_entries=cve_entries,
        cpe=first_cpe,
    )


def execute(spec: JobSpec, cred: CredentialMaterial) -> JobResult:
    if spec.driver_kind == "cli":
        if spec.kind == "cve_scan":
            return _run_cve_scan(spec, cred)
        return _run_cli(spec, cred)
    if spec.driver_kind == "netconf":
        return _run_netconf(spec, cred)
    raise ValueError(f"unknown driver kind: {spec.driver_kind!r}")
