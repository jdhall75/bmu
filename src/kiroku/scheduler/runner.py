"""Scheduler process.

Single-leader (Postgres advisory lock). Each tick:
  1. Recompute ``next_run_at`` for any schedule missing it.
  2. Find every enabled schedule whose ``next_run_at <= now``.
  3. For each one, get the schedule's job, expand job.device_groups to devices
     and union with job.devices (enabled filter), deduplicate by device id,
     persist ``Run`` rows in ``pending``, push ``JobSpec`` onto the Redis stream,
     and update the schedule's ``last_run_at`` / ``next_run_at``.

The advisory lock keeps two scheduler instances from double-firing. If we
lose the lock (or never get it), we sleep and try again.
"""

from __future__ import annotations

import signal
import time
from datetime import datetime, timezone

from croniter import croniter
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from kiroku.config import get_settings
from kiroku.db import session_scope
from kiroku.dispatch import fire_job
from kiroku.logging import configure_logging, get_logger
from kiroku.models import Job, Schedule
from kiroku.queue import ensure_consumer_group

log = get_logger(__name__)

_stop = False


def _install_signals() -> None:
    def _handler(signum, _frame):
        global _stop
        log.info("scheduler shutting down", signal=signum)
        _stop = True

    signal.signal(signal.SIGINT, _handler)
    signal.signal(signal.SIGTERM, _handler)


def _try_acquire_lock(db: Session, lock_id: int) -> bool:
    return bool(
        db.execute(
            text("SELECT pg_try_advisory_lock(:lock_id)"), {"lock_id": lock_id}
        ).scalar()
    )


def _release_lock(db: Session, lock_id: int) -> None:
    db.execute(text("SELECT pg_advisory_unlock(:lock_id)"), {"lock_id": lock_id})


def _next_fire(cron: str, tz_name: str, base: datetime) -> datetime:
    try:
        from zoneinfo import ZoneInfo

        tz = ZoneInfo(tz_name)
    except Exception:
        tz = timezone.utc
    base_local = base.astimezone(tz)
    itr = croniter(cron, base_local)
    return itr.get_next(datetime).astimezone(timezone.utc)


def _fire_due(db: Session, now: datetime) -> int:
    """Returns number of jobs queued."""
    queued = 0
    due = db.scalars(select(Schedule).where(Schedule.enabled.is_(True))).all()

    for sched in due:
        if sched.next_run_at is None:
            sched.next_run_at = _next_fire(sched.cron, sched.timezone, now)
            continue
        if sched.next_run_at > now:
            continue

        job: Job | None = sched.job
        if job is None:
            log.warning("schedule has no job; skipping", schedule=sched.name)
            sched.last_run_at = now
            sched.next_run_at = _next_fire(sched.cron, sched.timezone, now)
            continue

        batch = fire_job(job, db, schedule_id=sched.id, schedule_name=sched.name)
        fired = batch.total - batch.failed

        log.info(
            "schedule due",
            schedule=sched.name,
            job=job.name,
            kind=job.kind.value,
            devices=batch.total,
            queued=fired,
        )

        queued += fired
        sched.last_run_at = now
        sched.next_run_at = _next_fire(sched.cron, sched.timezone, now)

    return queued


def run_scheduler() -> None:
    configure_logging()
    settings = get_settings()
    _install_signals()

    ensure_consumer_group(settings.job_stream, settings.job_consumer_group)
    ensure_consumer_group(settings.result_stream, settings.result_consumer_group)

    log.info(
        "scheduler starting",
        tick_seconds=settings.scheduler_tick_seconds,
        lock_id=settings.scheduler_advisory_lock_id,
    )

    have_lock = False
    while not _stop:
        with session_scope() as db:
            if not have_lock:
                have_lock = _try_acquire_lock(db, settings.scheduler_advisory_lock_id)
                if not have_lock:
                    log.debug("waiting for scheduler lock")
                    time.sleep(settings.scheduler_tick_seconds)
                    continue
                log.info("acquired scheduler lock")

            now = datetime.now(tz=timezone.utc)
            try:
                queued = _fire_due(db, now)
                if queued:
                    log.info("tick complete", queued=queued)
            except Exception as exc:
                log.error("scheduler tick failed", error=str(exc), exc_info=True)

        for _ in range(settings.scheduler_tick_seconds):
            if _stop:
                break
            time.sleep(1)

    if have_lock:
        with session_scope() as db:
            _release_lock(db, settings.scheduler_advisory_lock_id)
        log.info("released scheduler lock")
