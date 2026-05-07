"""Recorder process.

Consumes the result stream, persists run outcomes, and (for backups) commits
the captured config to the on-disk git repo.
"""
from __future__ import annotations

import os
import signal
from datetime import datetime

from kiroku.db import session_scope
from kiroku.jobs import JobResult
from kiroku.logging import configure_logging, get_logger
from kiroku.models import CveResult, CveScan, Device, Run, RunStatus
from kiroku.queue import ack_result, read_results
from kiroku.recorder.git_store import GitStore

log = get_logger(__name__)

_stop = False


def _install_signals() -> None:
    def _handler(signum, _frame):
        global _stop
        log.info("recorder shutting down", signal=signum)
        _stop = True

    signal.signal(signal.SIGINT, _handler)
    signal.signal(signal.SIGTERM, _handler)


def _parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def _record_cve_scan(db, result: JobResult, run: Run) -> None:
    """Write CveScan + CveResult rows for a completed cve_scan job."""
    rows = result.parsed if isinstance(result.parsed, list) else ([result.parsed] if result.parsed else [])
    version_found = None
    raw_version = None
    for row in rows:
        if isinstance(row, dict) and row.get("version"):
            raw_version = str(row["version"])
            version_found = raw_version
            break

    scan = CveScan(
        run_id=result.run_id,
        device_id=result.device_id,
        cpe=result.cpe or "",
        version_found=version_found,
        raw_version=raw_version,
        scanned_at=_parse_iso(result.finished_at) or datetime.now(),
    )

    db.add(scan)
    db.flush()

    for entry in result.cve_entries:
        db.add(
            CveResult(
                scan_id=scan.id,
                cve_id=entry.get("cve_id", ""),
                cvss_v3_score=entry.get("cvss_v3_score"),
                severity=entry.get("severity"),
                summary=entry.get("summary"),
                published_at=_parse_iso(entry.get("published_at")),
                url=entry.get("url"),
            )
        )

    run.bytes_captured = len(result.cve_entries)


def _persist(result: JobResult, store: GitStore) -> None:
    with session_scope() as db:
        run = db.get(Run, result.run_id)
        if run is None:
            log.error("recorder: run not found", run_id=result.run_id)
            return

        run.started_at = _parse_iso(result.started_at) or run.started_at
        run.finished_at = _parse_iso(result.finished_at) or run.finished_at
        run.error = result.error

        if not result.success:
            run.status = RunStatus.FAILED
            return

        run.status = RunStatus.SUCCESS
        if result.kind == "backup" and result.config_text is not None:
            device = db.get(Device, result.device_id)
            group_name = device.group.name if device and device.group else "ungrouped"
            sha, payload_sha = store.write(
                group=group_name,
                device=result.device_name,
                content=result.config_text,
                author_note=f"run_id={result.run_id}",
            )
            run.commit_sha = sha
            run.payload_sha256 = payload_sha
            run.bytes_captured = len(result.config_text.encode("utf-8"))
        elif result.kind == "collect":
            run.bytes_captured = sum(
                len(c.output.encode("utf-8")) for c in result.command_results
            )
        elif result.kind == "cve_scan":
            _record_cve_scan(db, result, run)


def run_recorder() -> None:
    configure_logging()
    _install_signals()
    consumer = f"recorder-{os.getpid()}"
    store = GitStore()
    log.info("recorder starting", consumer=consumer, repo=str(store.root))

    while not _stop:
        try:
            results = read_results(consumer, count=8, block_ms=2000)
        except Exception as exc:
            log.error("read_results failed", error=str(exc))
            continue
        for msg_id, result in results:
            try:
                _persist(result, store)
                ack_result(msg_id)
            except Exception as exc:
                log.error("recorder persist failed",
                          run_id=result.run_id, error=str(exc), exc_info=True)
