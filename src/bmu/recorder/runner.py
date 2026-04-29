"""Recorder process.

Consumes the result stream, persists run outcomes, and (for backups) commits
the captured config to the on-disk git repo.
"""
from __future__ import annotations

import os
import signal
from datetime import datetime

from bmu.db import session_scope
from bmu.jobs import JobResult
from bmu.logging import configure_logging, get_logger
from bmu.models import Device, Run, RunStatus
from bmu.queue import ack_result, read_results
from bmu.recorder.git_store import GitStore

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
            # For now we just mark success; structured output ends up in logs.
            # Future: persist parsed rows into a dedicated table.
            run.bytes_captured = sum(
                len(c.output.encode("utf-8")) for c in result.command_results
            )


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
