"""Worker process.

Pulls JobSpecs off the Redis stream, resolves credentials, talks to the
device with scrapli, publishes a JobResult back, and acks the job.
"""
from __future__ import annotations

import os
import signal
from concurrent.futures import ThreadPoolExecutor

from kiroku.config import get_settings
from kiroku.credentials.registry import resolve_credential
from kiroku.db import session_scope
from kiroku.jobs import JobResult, JobSpec
from kiroku.logging import configure_logging, get_logger
from kiroku.models import Credential, Run, RunStatus
from kiroku.queue import ack_job, publish_result, read_jobs
from kiroku.worker.scrapli_runner import execute

log = get_logger(__name__)

_stop = False


def _install_signals() -> None:
    def _handler(signum, _frame):
        global _stop
        log.info("worker shutting down", signal=signum)
        _stop = True

    signal.signal(signal.SIGINT, _handler)
    signal.signal(signal.SIGTERM, _handler)


def _mark_running(run_id: int) -> None:
    from datetime import datetime, timezone

    with session_scope() as db:
        run = db.get(Run, run_id)
        if run:
            run.status = RunStatus.RUNNING
            run.started_at = datetime.now(tz=timezone.utc)


def _handle(msg_id: str, spec: JobSpec) -> None:
    log.info("job received", run_id=spec.run_id, device=spec.device_name, kind=spec.kind)
    _mark_running(spec.run_id)

    with session_scope() as db:
        cred_row = db.get(Credential, spec.credential.credential_id)
        if cred_row is None:
            result = JobResult(
                run_id=spec.run_id,
                device_id=spec.device_id,
                device_name=spec.device_name,
                kind=spec.kind,
                success=False,
                error=f"credential id {spec.credential.credential_id} not found",
                started_at="",
                finished_at="",
            )
            publish_result(result)
            ack_job(msg_id)
            return
        material = resolve_credential(cred_row)

    try:
        result = execute(spec, material)
    except Exception as exc:
        log.error("worker execute crashed",
                  device=spec.device_name, error=str(exc), exc_info=True)
        result = JobResult(
            run_id=spec.run_id,
            device_id=spec.device_id,
            device_name=spec.device_name,
            kind=spec.kind,
            success=False,
            error=f"{type(exc).__name__}: {exc}",
            started_at="",
            finished_at="",
        )

    publish_result(result)
    ack_job(msg_id)
    log.info("job completed", run_id=spec.run_id, device=spec.device_name,
             success=result.success)


def run_worker() -> None:
    configure_logging()
    settings = get_settings()
    _install_signals()
    consumer = f"worker-{os.getpid()}"

    log.info("worker starting", consumer=consumer,
             concurrency=settings.worker_concurrency)

    with ThreadPoolExecutor(max_workers=settings.worker_concurrency) as pool:
        while not _stop:
            try:
                jobs = read_jobs(consumer, count=settings.worker_concurrency,
                                 block_ms=2000)
            except Exception as exc:
                log.error("read_jobs failed", error=str(exc))
                continue
            for msg_id, spec in jobs:
                pool.submit(_handle, msg_id, spec)
