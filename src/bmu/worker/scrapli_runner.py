"""Run a JobSpec against a real device using scrapli (sync).

We use scrapli's platform driver registry when ``platform`` is a known
platform name; otherwise we fall back to ``GenericDriver`` and apply the
profile's prompt pattern / pre-commands / paging directives.
"""
from __future__ import annotations

import time
from datetime import datetime, timezone

from bmu.config import get_settings
from bmu.credentials.base import CredentialMaterial
from bmu.jobs import CommandResult, JobResult, JobSpec
from bmu.logging import get_logger
from bmu.worker.parsers import parse

log = get_logger(__name__)


def _now_iso() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


def _build_cli_driver(spec: JobSpec, cred: CredentialMaterial):
    """Return an opened scrapli connection ready for ``send_command*``."""
    settings = get_settings()
    common = {
        "host": spec.hostname,
        "port": spec.port or 22,
        "auth_username": cred.username,
        "auth_password": cred.password or "",
        "auth_secondary": cred.enable_password or "",
        "auth_strict_key": False,
        "transport": "system" if spec.transport != "telnet" else "telnet",
        "timeout_socket": settings.worker_connect_timeout,
        "timeout_transport": settings.worker_connect_timeout,
        "timeout_ops": settings.worker_command_timeout,
    }
    if cred.private_key:
        # scrapli wants a path; for MVP we expect inline keys to be written
        # into a tmpfile. Keep simple - require password auth for now if no
        # path is supplied.
        common["auth_private_key"] = cred.private_key

    platform = (spec.platform or "generic").lower()
    if platform == "generic":
        from scrapli.driver import GenericDriver

        kwargs = dict(common)
        if spec.prompt_pattern:
            kwargs["comms_prompt_pattern"] = spec.prompt_pattern
        return GenericDriver(**kwargs)

    from scrapli import Scrapli

    return Scrapli(platform=platform, **common)


def _run_cli(spec: JobSpec, cred: CredentialMaterial) -> JobResult:
    started = _now_iso()
    driver = _build_cli_driver(spec, cred)
    config_chunks: list[str] = []
    cmd_results: list[CommandResult] = []
    error: str | None = None
    try:
        driver.open()
        try:
            for pre in spec.pre_commands:
                driver.send_command(pre)
            if spec.disable_paging_command:
                driver.send_command(spec.disable_paging_command)
            for cmd in spec.commands:
                t0 = time.perf_counter()
                resp = driver.send_command(cmd)
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
        finally:
            driver.close()
    except Exception as exc:
        error = f"{type(exc).__name__}: {exc}"
        log.error("CLI run failed", device=spec.device_name, error=error)

    parsed = None
    if spec.kind == "collect" and spec.parser_type and cmd_results:
        joined = "\n".join(c.output for c in cmd_results)
        try:
            parsed = parse(spec.parser_type, spec.parser_body, joined)
        except Exception as exc:
            log.error("parser failed", device=spec.device_name, error=str(exc))

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
    )


def _run_netconf(spec: JobSpec, cred: CredentialMaterial) -> JobResult:
    started = _now_iso()
    error: str | None = None
    raw_xml: str | None = None
    parsed = None

    try:
        from scrapli_netconf.driver import NetconfDriver

        settings = get_settings()
        driver = NetconfDriver(
            host=spec.hostname,
            port=spec.port or 830,
            auth_username=cred.username,
            auth_password=cred.password or "",
            auth_strict_key=False,
            transport="system",
            timeout_socket=settings.worker_connect_timeout,
            timeout_transport=settings.worker_connect_timeout,
            timeout_ops=settings.worker_command_timeout,
        )
        driver.open()
        try:
            if not spec.rpc:
                raise ValueError("netconf profile is missing rpc")
            resp = driver.rpc(filter_=spec.rpc)
            raw_xml = resp.result
        finally:
            driver.close()
    except Exception as exc:
        error = f"{type(exc).__name__}: {exc}"
        log.error("NETCONF run failed", device=spec.device_name, error=error)

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
    )


def _run_cve_scan(spec: JobSpec, cred: CredentialMaterial) -> JobResult:
    """Run commands, parse version output, then query the CVE API.

    Command execution and parsing is identical to a collect run. The CVE
    lookup is delegated to bmu.cve (implemented in Phase 3); until that
    module exists, cve_entries is left empty.
    """
    started = _now_iso()
    driver = _build_cli_driver(spec, cred)
    cmd_results: list[CommandResult] = []
    error: str | None = None
    try:
        driver.open()
        try:
            for pre in spec.pre_commands:
                driver.send_command(pre)
            if spec.disable_paging_command:
                driver.send_command(spec.disable_paging_command)
            for cmd in spec.commands:
                t0 = time.perf_counter()
                resp = driver.send_command(cmd)
                elapsed_ms = int((time.perf_counter() - t0) * 1000)
                cmd_results.append(
                    CommandResult(
                        command=cmd,
                        output=resp.result,
                        elapsed_ms=elapsed_ms,
                        failed=resp.failed,
                    )
                )
        finally:
            driver.close()
    except Exception as exc:
        error = f"{type(exc).__name__}: {exc}"
        log.error("CVE scan CLI run failed", device=spec.device_name, error=error)

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
        from bmu.cve import query_cpe

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
    if spec.profile_kind == "cli":
        if spec.kind == "cve_scan":
            return _run_cve_scan(spec, cred)
        return _run_cli(spec, cred)
    if spec.profile_kind == "netconf":
        return _run_netconf(spec, cred)
    raise ValueError(f"unknown profile kind: {spec.profile_kind!r}")
