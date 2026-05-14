"""Worker process.

Pulls JobSpecs off the Redis stream, executes them against the device via
scrapli, and publishes a JobResult back.  The worker is intentionally
database-free: credentials are resolved by the dispatcher and embedded in
the JobSpec so this process only needs Redis reachability and network access
to the managed devices.
"""

from __future__ import annotations

import os
import signal
import traceback
from concurrent.futures import ProcessPoolExecutor
from datetime import datetime, timezone

from kiroku.config import get_settings
from kiroku.credentials.base import CredentialMaterial
from kiroku.jobs import JobResult, JobSpec
from kiroku.logging import configure_logging, get_logger
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


def _handle(msg_id: str, spec: JobSpec) -> None:
    log.info(
        "job received", run_id=spec.run_id, device=spec.device_name, kind=spec.kind
    )

    now = datetime.now(tz=timezone.utc).isoformat()

    if spec.credential_material is None:
        result = JobResult(
            run_id=spec.run_id,
            device_id=spec.device_id,
            device_name=spec.device_name,
            kind=spec.kind,
            success=False,
            error="job spec has no embedded credential_material; re-dispatch from an updated server",
            started_at=now,
            finished_at=now,
        )
        publish_result(result)
        ack_job(msg_id)
        return

    material = CredentialMaterial(
        username=spec.credential_material.username,
        password=spec.credential_material.password,
        enable_password=spec.credential_material.enable_password,
        private_key=spec.credential_material.private_key,
        private_key_passphrase=spec.credential_material.private_key_passphrase,
    )

    try:
        result = execute(spec, material)
    except Exception as exc:
        tb = traceback.format_exc()
        log.error(
            "worker execute crashed",
            device=spec.device_name,
            error=str(exc),
            exc_info=True,
        )
        now = datetime.now(tz=timezone.utc).isoformat()
        result = JobResult(
            run_id=spec.run_id,
            device_id=spec.device_id,
            device_name=spec.device_name,
            kind=spec.kind,
            success=False,
            error=f"{type(exc).__name__}: {exc}\n\n{tb}",
            started_at=now,
            finished_at=now,
        )

    publish_result(result)
    ack_job(msg_id)
    log.info(
        "job completed",
        run_id=spec.run_id,
        device=spec.device_name,
        success=result.success,
    )


def run_worker() -> None:
    configure_logging()
    settings = get_settings()
    _install_signals()
    consumer = f"worker-{os.getpid()}"

    log.info(
        "worker starting", consumer=consumer, concurrency=settings.worker_concurrency
    )

    with ProcessPoolExecutor(max_workers=settings.worker_concurrency) as pool:
        while not _stop:
            try:
                jobs = read_jobs(
                    consumer, count=settings.worker_concurrency, block_ms=2000
                )
            except Exception as exc:
                log.error("read_jobs failed", error=str(exc))
                continue
            for msg_id, spec in jobs:
                future = pool.submit(_handle, msg_id, spec)
                future.add_done_callback(
                    lambda f: (
                        f.exception()
                        and log.error("job subprocess failed", error=str(f.exception()))
                    )
                )
