"""Recorder process.

Consumes the result stream, persists run outcomes, and (for backups) commits
the captured config to the on-disk git repo.

Batch git commits: the scheduler writes a RunBatch row with the exact device
count (total) before dispatching. As results arrive, files are staged but not
committed. When succeeded + failed reaches total the whole batch is committed
in a single git operation.
"""
from __future__ import annotations

import os
import signal
from datetime import datetime

from sqlalchemy import select, text

from kiroku.db import session_scope
from kiroku.jobs import JobResult
from kiroku.logging import configure_logging, get_logger
from kiroku.models import CveResult, CveScan, Device, Run, RunBatch, RunStatus
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


def _persist(result: JobResult, store: GitStore, batch_staged: dict[int, list[str]]) -> None:
    """Persist one job result. batch_staged accumulates changed file paths per batch_id."""
    with session_scope() as db:
        run = db.get(Run, result.run_id)
        if run is None:
            log.error("recorder: run not found", run_id=result.run_id)
            return

        batch: RunBatch | None = db.get(RunBatch, run.batch_id) if run.batch_id else None

        run.started_at = _parse_iso(result.started_at) or run.started_at
        run.finished_at = _parse_iso(result.finished_at) or run.finished_at
        run.error = result.error

        if not result.success:
            run.status = RunStatus.FAILED
            if batch:
                batch.failed += 1
        else:
            run.status = RunStatus.SUCCESS
            if batch:
                batch.succeeded += 1

            if result.kind == "backup" and result.config_text is not None:
                device = db.get(Device, result.device_id)
                group_name = device.group.name if device and device.group else "ungrouped"
                rel_path = store.file_path(group=group_name, device=result.device_name)

                if batch:
                    changed, payload_sha = store.stage(
                        group=group_name,
                        device=result.device_name,
                        content=result.config_text,
                    )
                    if changed:
                        batch_staged.setdefault(batch.id, []).append(rel_path)
                else:
                    # No batch context (manual/ad-hoc run): commit immediately.
                    sha, payload_sha = store.write(
                        group=group_name,
                        device=result.device_name,
                        content=result.config_text,
                        author_note=f"run_id={result.run_id}",
                    )
                    run.commit_sha = sha

                run.payload_sha256 = payload_sha
                run.bytes_captured = len(result.config_text.encode("utf-8"))
                captured_at = _parse_iso(result.finished_at)
                if device:
                    device.latest_backup_path = rel_path
                    device.latest_backup_at = captured_at

                db.execute(text("""
                    INSERT INTO device_configs (device_id, batch_id, captured_at, content, content_fts)
                    VALUES (:device_id, :batch_id, :captured_at, :content,
                            to_tsvector('simple', :content))
                    ON CONFLICT (device_id) DO UPDATE SET
                        batch_id = EXCLUDED.batch_id,
                        captured_at = EXCLUDED.captured_at,
                        content = EXCLUDED.content,
                        content_fts = EXCLUDED.content_fts
                """), {
                    "device_id": result.device_id,
                    "batch_id": run.batch_id,
                    "captured_at": captured_at,
                    "content": result.config_text,
                })

            elif result.kind == "collect":
                run.bytes_captured = sum(
                    len(c.output.encode("utf-8")) for c in result.command_results
                )
            elif result.kind == "cve_scan":
                _record_cve_scan(db, result, run)

        # When the last result of a batch arrives, commit git and close the batch.
        if batch and batch.finished_at is None:
            done = batch.succeeded + batch.failed
            if done >= batch.total:
                batch.finished_at = _parse_iso(result.finished_at) or datetime.now()
                changed_paths = batch_staged.pop(batch.id, [])
                if changed_paths:
                    msg = (
                        f"backup batch: {batch.schedule_name}\n\n"
                        f"batch_id={batch.id}, devices={batch.total}\n"
                        + "\n".join(changed_paths)
                    )
                    commit_sha = store.commit_batch(changed_paths, msg)
                    if commit_sha:
                        batch.commit_sha = commit_sha
                        # Stamp all runs in this batch with the shared commit sha.
                        for r in db.scalars(
                            select(Run).where(Run.batch_id == batch.id)
                        ).all():
                            r.commit_sha = commit_sha
                log.info(
                    "batch complete",
                    batch_id=batch.id,
                    schedule=batch.schedule_name,
                    total=batch.total,
                    succeeded=batch.succeeded,
                    failed=batch.failed,
                )


def run_recorder() -> None:
    configure_logging()
    _install_signals()
    consumer = f"recorder-{os.getpid()}"
    store = GitStore()
    # In-memory accumulator: batch_id → [relative file paths staged but not yet committed]
    batch_staged: dict[int, list[str]] = {}
    log.info("recorder starting", consumer=consumer, repo=str(store.root))

    while not _stop:
        try:
            results = read_results(consumer, count=8, block_ms=2000)
        except Exception as exc:
            log.error("read_results failed", error=str(exc))
            continue
        for msg_id, result in results:
            try:
                _persist(result, store, batch_staged)
                ack_result(msg_id)
            except Exception as exc:
                log.error(
                    "recorder persist failed",
                    run_id=result.run_id,
                    error=str(exc),
                    exc_info=True,
                )
