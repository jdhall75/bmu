"""Thin Redis Streams helpers for job dispatch and result collection."""

from __future__ import annotations

import json
from typing import Iterable

import redis

from kiroku.config import get_settings
from kiroku.jobs import JobResult, JobSpec
from kiroku.logging import get_logger

log = get_logger(__name__)


def _client() -> redis.Redis:
    return redis.Redis.from_url(get_settings().redis_url, decode_responses=True)


def ensure_consumer_group(stream: str, group: str) -> None:
    r = _client()
    try:
        r.xgroup_create(name=stream, groupname=group, id="$", mkstream=True)
    except redis.ResponseError as exc:
        if "BUSYGROUP" not in str(exc):
            raise


def _job_stream_for(spec: JobSpec) -> str:
    settings = get_settings()
    if spec.worker_pool:
        return f"{settings.job_stream}:{spec.worker_pool}"
    return settings.job_stream


def publish_job(spec: JobSpec) -> str:
    r = _client()
    stream = _job_stream_for(spec)
    payload = spec.model_dump_json()
    msg_id = r.xadd(stream, {"data": payload})
    log.debug(
        "queued job",
        run_id=spec.run_id,
        device=spec.device_name,
        stream=stream,
        msg_id=msg_id,
    )
    return msg_id


def publish_result(result: JobResult) -> str:
    settings = get_settings()
    r = _client()
    msg_id = r.xadd(settings.result_stream, {"data": result.model_dump_json()})
    return msg_id


def read_jobs(
    consumer: str, *, count: int = 1, block_ms: int = 5000
) -> list[tuple[str, JobSpec]]:
    settings = get_settings()
    r = _client()
    stream = settings.effective_job_stream
    ensure_consumer_group(stream, settings.job_consumer_group)
    entries = r.xreadgroup(
        groupname=settings.job_consumer_group,
        consumername=consumer,
        streams={stream: ">"},
        count=count,
        block=block_ms,
    )
    return list(_unpack(entries, JobSpec))


def read_results(
    consumer: str, *, count: int = 8, block_ms: int = 5000
) -> list[tuple[str, JobResult]]:
    settings = get_settings()
    r = _client()
    ensure_consumer_group(settings.result_stream, settings.result_consumer_group)
    entries = r.xreadgroup(
        groupname=settings.result_consumer_group,
        consumername=consumer,
        streams={settings.result_stream: ">"},
        count=count,
        block=block_ms,
    )
    return list(_unpack(entries, JobResult))


def ack_job(msg_id: str) -> None:
    settings = get_settings()
    _client().xack(settings.effective_job_stream, settings.job_consumer_group, msg_id)


def ack_result(msg_id: str) -> None:
    settings = get_settings()
    _client().xack(settings.result_stream, settings.result_consumer_group, msg_id)


def job_stream_names() -> list[str]:
    """Return all active job stream names (default + any worker-pool variants)."""
    settings = get_settings()
    r = _client()
    names: list[str] = []
    for key in r.scan_iter(match=f"{settings.job_stream}*", count=100):
        names.append(key)
    return names or [settings.job_stream]


def purge_undelivered(stream: str, group: str) -> list[tuple[str, int]]:
    """Delete messages not yet claimed by any consumer.

    Returns (msg_id, run_id) for each message removed so the caller can
    cancel the corresponding Run rows.
    """
    r = _client()
    try:
        groups = r.xinfo_groups(stream)
    except redis.ResponseError:
        return []

    last_delivered = "0-0"
    for g in groups:
        if g["name"] == group:
            last_delivered = g["last-delivered-id"]
            break

    # XREAD returns entries with ID strictly > last_delivered (undelivered).
    try:
        raw = r.xread(streams={stream: last_delivered}, count=10_000)
    except redis.ResponseError:
        return []

    if not raw:
        return []

    msg_ids: list[str] = []
    results: list[tuple[str, int]] = []
    for _stream_name, entries in raw:
        for msg_id, fields in entries:
            msg_ids.append(msg_id)
            data = fields.get("data")
            if data:
                try:
                    spec = JobSpec.model_validate_json(data)
                    results.append((msg_id, spec.run_id))
                except Exception:
                    pass

    if msg_ids:
        r.xdel(stream, *msg_ids)
        log.info("purged undelivered jobs", stream=stream, count=len(msg_ids))

    return results


def _unpack(entries, model_cls) -> Iterable[tuple[str, object]]:
    if not entries:
        return
    for _stream, msgs in entries:
        for msg_id, fields in msgs:
            data = fields.get("data")
            if not data:
                continue
            try:
                yield msg_id, model_cls.model_validate_json(data)
            except Exception as exc:
                log.error(
                    "failed to decode stream entry", msg_id=msg_id, error=str(exc)
                )
