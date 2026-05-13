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


def publish_job(spec: JobSpec) -> str:
    settings = get_settings()
    r = _client()
    payload = spec.model_dump_json()
    msg_id = r.xadd(settings.job_stream, {"data": payload})
    log.debug("queued job", run_id=spec.run_id, device=spec.device_name, msg_id=msg_id)
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
    ensure_consumer_group(settings.job_stream, settings.job_consumer_group)
    entries = r.xreadgroup(
        groupname=settings.job_consumer_group,
        consumername=consumer,
        streams={settings.job_stream: ">"},
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
    _client().xack(settings.job_stream, settings.job_consumer_group, msg_id)


def ack_result(msg_id: str) -> None:
    settings = get_settings()
    _client().xack(settings.result_stream, settings.result_consumer_group, msg_id)


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
