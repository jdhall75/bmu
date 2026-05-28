"""Tests for kiroku.queue — all Redis calls are mocked."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, call, patch

import pytest
import redis

from kiroku.jobs import JobResult, JobSpec
from kiroku.queue import (
    _job_stream_for,
    _unpack,
    ack_job,
    ack_result,
    ensure_consumer_group,
    job_stream_names,
    publish_job,
    publish_result,
    purge_undelivered,
    read_jobs,
    read_results,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _mock_settings(
    *,
    job_stream: str = "kiroku:jobs",
    result_stream: str = "kiroku:results",
    job_consumer_group: str = "kiroku-workers",
    result_consumer_group: str = "kiroku-recorders",
    effective_job_stream: str = "kiroku:jobs",
    redis_url: str = "redis://localhost:6379/0",
):
    s = MagicMock()
    s.job_stream = job_stream
    s.result_stream = result_stream
    s.job_consumer_group = job_consumer_group
    s.result_consumer_group = result_consumer_group
    s.effective_job_stream = effective_job_stream
    s.redis_url = redis_url
    return s


def _make_spec(**kwargs) -> JobSpec:
    defaults = dict(
        run_id=1,
        device_id=10,
        device_name="router1",
        hostname="192.168.1.1",
        kind="backup",
        job_id=5,
        driver_kind="cli",
        platform="cisco_iosxe",
        credential=MagicMock(provider="local", credential_id=1, ref=None),
        worker_pool=None,
    )
    defaults.update(kwargs)
    spec = MagicMock(spec=JobSpec)
    for k, v in defaults.items():
        setattr(spec, k, v)
    spec.model_dump_json.return_value = json.dumps({"run_id": defaults["run_id"]})
    return spec


def _make_result(**kwargs) -> JobResult:
    r = MagicMock(spec=JobResult)
    r.model_dump_json.return_value = json.dumps({"run_id": kwargs.get("run_id", 1)})
    return r


# ---------------------------------------------------------------------------
# ensure_consumer_group
# ---------------------------------------------------------------------------


class TestEnsureConsumerGroup:
    def _mock_client(self):
        return MagicMock()

    def test_creates_group_with_mkstream(self):
        mock_redis = self._mock_client()
        with patch("kiroku.queue._client", return_value=mock_redis):
            ensure_consumer_group("mystream", "mygroup")
        mock_redis.xgroup_create.assert_called_once_with(
            name="mystream", groupname="mygroup", id="$", mkstream=True
        )

    def test_busygroup_error_is_swallowed(self):
        mock_redis = self._mock_client()
        mock_redis.xgroup_create.side_effect = redis.ResponseError("BUSYGROUP Consumer Group already exists")
        with patch("kiroku.queue._client", return_value=mock_redis):
            ensure_consumer_group("mystream", "mygroup")  # should not raise

    def test_other_redis_error_propagates(self):
        mock_redis = self._mock_client()
        mock_redis.xgroup_create.side_effect = redis.ResponseError("some other error")
        with patch("kiroku.queue._client", return_value=mock_redis):
            with pytest.raises(redis.ResponseError, match="some other error"):
                ensure_consumer_group("mystream", "mygroup")


# ---------------------------------------------------------------------------
# _job_stream_for
# ---------------------------------------------------------------------------


class TestJobStreamFor:
    def test_no_worker_pool_returns_default_stream(self):
        settings = _mock_settings()
        spec = _make_spec(worker_pool=None)
        with patch("kiroku.queue.get_settings", return_value=settings):
            result = _job_stream_for(spec)
        assert result == "kiroku:jobs"

    def test_worker_pool_appended_to_stream(self):
        settings = _mock_settings()
        spec = _make_spec(worker_pool="datacenter-1")
        with patch("kiroku.queue.get_settings", return_value=settings):
            result = _job_stream_for(spec)
        assert result == "kiroku:jobs:datacenter-1"


# ---------------------------------------------------------------------------
# publish_job
# ---------------------------------------------------------------------------


class TestPublishJob:
    def test_returns_msg_id(self):
        mock_redis = MagicMock()
        mock_redis.xadd.return_value = "1234-0"
        settings = _mock_settings()
        spec = _make_spec()
        with patch("kiroku.queue._client", return_value=mock_redis), \
             patch("kiroku.queue.get_settings", return_value=settings):
            result = publish_job(spec)
        assert result == "1234-0"

    def test_xadd_called_with_data(self):
        mock_redis = MagicMock()
        mock_redis.xadd.return_value = "1-0"
        settings = _mock_settings()
        spec = _make_spec()
        with patch("kiroku.queue._client", return_value=mock_redis), \
             patch("kiroku.queue.get_settings", return_value=settings):
            publish_job(spec)
        mock_redis.xadd.assert_called_once()
        args, kwargs = mock_redis.xadd.call_args
        assert args[0] == "kiroku:jobs"
        assert "data" in args[1]

    def test_worker_pool_routes_to_pool_stream(self):
        mock_redis = MagicMock()
        mock_redis.xadd.return_value = "1-0"
        settings = _mock_settings()
        spec = _make_spec(worker_pool="pool-a")
        with patch("kiroku.queue._client", return_value=mock_redis), \
             patch("kiroku.queue.get_settings", return_value=settings):
            publish_job(spec)
        stream_arg = mock_redis.xadd.call_args[0][0]
        assert stream_arg == "kiroku:jobs:pool-a"


# ---------------------------------------------------------------------------
# publish_result
# ---------------------------------------------------------------------------


class TestPublishResult:
    def test_returns_msg_id(self):
        mock_redis = MagicMock()
        mock_redis.xadd.return_value = "99-0"
        settings = _mock_settings()
        result = _make_result()
        with patch("kiroku.queue._client", return_value=mock_redis), \
             patch("kiroku.queue.get_settings", return_value=settings):
            msg_id = publish_result(result)
        assert msg_id == "99-0"

    def test_xadd_targets_result_stream(self):
        mock_redis = MagicMock()
        mock_redis.xadd.return_value = "1-0"
        settings = _mock_settings()
        result = _make_result()
        with patch("kiroku.queue._client", return_value=mock_redis), \
             patch("kiroku.queue.get_settings", return_value=settings):
            publish_result(result)
        stream_arg = mock_redis.xadd.call_args[0][0]
        assert stream_arg == "kiroku:results"


# ---------------------------------------------------------------------------
# read_jobs / read_results
# ---------------------------------------------------------------------------


class TestReadJobs:
    def test_returns_empty_when_no_entries(self):
        mock_redis = MagicMock()
        mock_redis.xreadgroup.return_value = []
        settings = _mock_settings()
        with patch("kiroku.queue._client", return_value=mock_redis), \
             patch("kiroku.queue.get_settings", return_value=settings), \
             patch("kiroku.queue.ensure_consumer_group"):
            result = read_jobs("worker-1")
        assert result == []

    def test_calls_xreadgroup_with_correct_args(self):
        mock_redis = MagicMock()
        mock_redis.xreadgroup.return_value = []
        settings = _mock_settings()
        with patch("kiroku.queue._client", return_value=mock_redis), \
             patch("kiroku.queue.get_settings", return_value=settings), \
             patch("kiroku.queue.ensure_consumer_group"):
            read_jobs("worker-1", count=4, block_ms=1000)
        mock_redis.xreadgroup.assert_called_once_with(
            groupname="kiroku-workers",
            consumername="worker-1",
            streams={"kiroku:jobs": ">"},
            count=4,
            block=1000,
        )


class TestReadResults:
    def test_returns_empty_when_no_entries(self):
        mock_redis = MagicMock()
        mock_redis.xreadgroup.return_value = []
        settings = _mock_settings()
        with patch("kiroku.queue._client", return_value=mock_redis), \
             patch("kiroku.queue.get_settings", return_value=settings), \
             patch("kiroku.queue.ensure_consumer_group"):
            result = read_results("recorder-1")
        assert result == []

    def test_calls_xreadgroup_targeting_result_stream(self):
        mock_redis = MagicMock()
        mock_redis.xreadgroup.return_value = []
        settings = _mock_settings()
        with patch("kiroku.queue._client", return_value=mock_redis), \
             patch("kiroku.queue.get_settings", return_value=settings), \
             patch("kiroku.queue.ensure_consumer_group"):
            read_results("recorder-1")
        stream_kwarg = mock_redis.xreadgroup.call_args.kwargs["streams"]
        assert "kiroku:results" in stream_kwarg


# ---------------------------------------------------------------------------
# ack_job / ack_result
# ---------------------------------------------------------------------------


class TestAck:
    def test_ack_job_calls_xack(self):
        mock_redis = MagicMock()
        settings = _mock_settings()
        with patch("kiroku.queue._client", return_value=mock_redis), \
             patch("kiroku.queue.get_settings", return_value=settings):
            ack_job("5-0")
        mock_redis.xack.assert_called_once_with("kiroku:jobs", "kiroku-workers", "5-0")

    def test_ack_result_calls_xack(self):
        mock_redis = MagicMock()
        settings = _mock_settings()
        with patch("kiroku.queue._client", return_value=mock_redis), \
             patch("kiroku.queue.get_settings", return_value=settings):
            ack_result("7-0")
        mock_redis.xack.assert_called_once_with("kiroku:results", "kiroku-recorders", "7-0")


# ---------------------------------------------------------------------------
# job_stream_names
# ---------------------------------------------------------------------------


class TestJobStreamNames:
    def test_returns_found_streams(self):
        mock_redis = MagicMock()
        mock_redis.scan_iter.return_value = ["kiroku:jobs", "kiroku:jobs:pool-a"]
        settings = _mock_settings()
        with patch("kiroku.queue._client", return_value=mock_redis), \
             patch("kiroku.queue.get_settings", return_value=settings):
            result = job_stream_names()
        assert "kiroku:jobs" in result
        assert "kiroku:jobs:pool-a" in result

    def test_falls_back_to_default_when_scan_empty(self):
        mock_redis = MagicMock()
        mock_redis.scan_iter.return_value = []
        settings = _mock_settings()
        with patch("kiroku.queue._client", return_value=mock_redis), \
             patch("kiroku.queue.get_settings", return_value=settings):
            result = job_stream_names()
        assert result == ["kiroku:jobs"]

    def test_scan_iter_uses_wildcard_match(self):
        mock_redis = MagicMock()
        mock_redis.scan_iter.return_value = []
        settings = _mock_settings()
        with patch("kiroku.queue._client", return_value=mock_redis), \
             patch("kiroku.queue.get_settings", return_value=settings):
            job_stream_names()
        mock_redis.scan_iter.assert_called_once_with(match="kiroku:jobs*", count=100)


# ---------------------------------------------------------------------------
# purge_undelivered
# ---------------------------------------------------------------------------


def _make_job_spec_json(run_id: int) -> str:
    return json.dumps({
        "run_id": run_id,
        "device_id": 1,
        "device_name": "r1",
        "hostname": "10.0.0.1",
        "kind": "backup",
        "job_id": 1,
        "driver_kind": "cli",
        "credential": {"provider": "local", "credential_id": 1, "ref": None},
    })


class TestPurgeUndelivered:
    def test_returns_empty_when_stream_not_found(self):
        mock_redis = MagicMock()
        mock_redis.xinfo_groups.side_effect = redis.ResponseError("no such key")
        with patch("kiroku.queue._client", return_value=mock_redis):
            result = purge_undelivered("kiroku:jobs", "kiroku-workers")
        assert result == []

    def test_returns_empty_when_xread_fails(self):
        mock_redis = MagicMock()
        mock_redis.xinfo_groups.return_value = [{"name": "kiroku-workers", "last-delivered-id": "0-0"}]
        mock_redis.xread.side_effect = redis.ResponseError("err")
        with patch("kiroku.queue._client", return_value=mock_redis):
            result = purge_undelivered("kiroku:jobs", "kiroku-workers")
        assert result == []

    def test_returns_empty_when_no_undelivered_messages(self):
        mock_redis = MagicMock()
        mock_redis.xinfo_groups.return_value = [{"name": "kiroku-workers", "last-delivered-id": "5-0"}]
        mock_redis.xread.return_value = []
        with patch("kiroku.queue._client", return_value=mock_redis):
            result = purge_undelivered("kiroku:jobs", "kiroku-workers")
        assert result == []

    def test_happy_path_deletes_messages_and_returns_run_ids(self):
        mock_redis = MagicMock()
        mock_redis.xinfo_groups.return_value = [{"name": "kiroku-workers", "last-delivered-id": "3-0"}]
        entry1 = ("4-0", {"data": _make_job_spec_json(42)})
        entry2 = ("5-0", {"data": _make_job_spec_json(43)})
        mock_redis.xread.return_value = [("kiroku:jobs", [entry1, entry2])]
        with patch("kiroku.queue._client", return_value=mock_redis):
            result = purge_undelivered("kiroku:jobs", "kiroku-workers")
        assert ("4-0", 42) in result
        assert ("5-0", 43) in result
        mock_redis.xdel.assert_called_once_with("kiroku:jobs", "4-0", "5-0")

    def test_invalid_json_skipped_but_still_deleted(self):
        mock_redis = MagicMock()
        mock_redis.xinfo_groups.return_value = [{"name": "kiroku-workers", "last-delivered-id": "0-0"}]
        entry = ("1-0", {"data": "not valid json"})
        mock_redis.xread.return_value = [("kiroku:jobs", [entry])]
        with patch("kiroku.queue._client", return_value=mock_redis):
            result = purge_undelivered("kiroku:jobs", "kiroku-workers")
        # deleted but no (msg_id, run_id) in results since JSON was invalid
        assert result == []
        mock_redis.xdel.assert_called_once_with("kiroku:jobs", "1-0")

    def test_group_not_found_uses_zero_last_delivered(self):
        mock_redis = MagicMock()
        # Group with a different name — our group not in list
        mock_redis.xinfo_groups.return_value = [{"name": "other-group", "last-delivered-id": "99-0"}]
        mock_redis.xread.return_value = []
        with patch("kiroku.queue._client", return_value=mock_redis):
            purge_undelivered("kiroku:jobs", "kiroku-workers")
        # Should read from "0-0" (default)
        mock_redis.xread.assert_called_once_with(streams={"kiroku:jobs": "0-0"}, count=10_000)

    def test_no_data_field_in_entry_skipped(self):
        mock_redis = MagicMock()
        mock_redis.xinfo_groups.return_value = [{"name": "kiroku-workers", "last-delivered-id": "0-0"}]
        entry = ("1-0", {})  # no "data" key
        mock_redis.xread.return_value = [("kiroku:jobs", [entry])]
        with patch("kiroku.queue._client", return_value=mock_redis):
            result = purge_undelivered("kiroku:jobs", "kiroku-workers")
        assert result == []
        mock_redis.xdel.assert_called_once_with("kiroku:jobs", "1-0")


# ---------------------------------------------------------------------------
# _unpack
# ---------------------------------------------------------------------------


class TestUnpack:
    def test_empty_entries_yields_nothing(self):
        assert list(_unpack([], JobSpec)) == []

    def test_none_entries_yields_nothing(self):
        assert list(_unpack(None, JobSpec)) == []

    def test_valid_json_yields_tuple(self):
        data = _make_job_spec_json(7)
        entries = [("kiroku:jobs", [("1-0", {"data": data})])]
        result = list(_unpack(entries, JobSpec))
        assert len(result) == 1
        msg_id, spec = result[0]
        assert msg_id == "1-0"
        assert spec.run_id == 7

    def test_missing_data_field_skipped(self):
        entries = [("kiroku:jobs", [("1-0", {})])]
        result = list(_unpack(entries, JobSpec))
        assert result == []

    def test_invalid_json_skipped(self):
        entries = [("kiroku:jobs", [("1-0", {"data": "bad json"})])]
        result = list(_unpack(entries, JobSpec))
        assert result == []

    def test_multiple_entries_all_yielded(self):
        entries = [
            ("kiroku:jobs", [
                ("1-0", {"data": _make_job_spec_json(1)}),
                ("2-0", {"data": _make_job_spec_json(2)}),
            ])
        ]
        result = list(_unpack(entries, JobSpec))
        assert len(result) == 2
        assert result[0][0] == "1-0"
        assert result[1][0] == "2-0"
