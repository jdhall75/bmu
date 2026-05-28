"""Tests for kiroku.scheduler.runner.

All external I/O (Postgres advisory locks, Redis, signal registration) is
patched.  No live database or Redis connection is required.
"""

from __future__ import annotations

import signal
from contextlib import contextmanager
from datetime import datetime, timezone
from unittest.mock import MagicMock, call, patch

import pytest

import kiroku.scheduler.runner as sched_mod
from kiroku.scheduler.runner import (
    _fire_due,
    _install_signals,
    _next_fire,
    _release_lock,
    _try_acquire_lock,
    run_scheduler,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class FakeSchedule:
    """Minimal mutable stand-in for a Schedule ORM row."""

    def __init__(self, **kwargs):
        self.id = 1
        self.name = "test-schedule"
        self.cron = "* * * * *"
        self.timezone = "UTC"
        self.enabled = True
        self.next_run_at = None
        self.last_run_at = None
        self.skip_next_run = False
        self.job = None
        for k, v in kwargs.items():
            setattr(self, k, v)


class FakeJob:
    """Minimal stand-in for a Job ORM row."""

    def __init__(self, **kwargs):
        self.id = 1
        self.name = "test-job"
        self.kind = MagicMock(value="backup")
        for k, v in kwargs.items():
            setattr(self, k, v)


def make_db(schedules: list) -> MagicMock:
    db = MagicMock()
    db.scalars.return_value.all.return_value = schedules
    return db


def make_batch(total: int = 3, failed: int = 0) -> MagicMock:
    b = MagicMock()
    b.total = total
    b.failed = failed
    return b


_NOW = datetime(2025, 6, 1, 12, 0, tzinfo=timezone.utc)
_PAST = datetime(2025, 6, 1, 10, 0, tzinfo=timezone.utc)
_FUTURE = datetime(2025, 6, 1, 14, 0, tzinfo=timezone.utc)


# ---------------------------------------------------------------------------
# _next_fire
# ---------------------------------------------------------------------------


class TestNextFire:
    def test_result_is_strictly_after_base(self):
        result = _next_fire("* * * * *", "UTC", _NOW)
        assert result > _NOW

    def test_result_is_utc_aware(self):
        result = _next_fire("0 * * * *", "UTC", _NOW)
        assert result.tzinfo is not None
        assert result.utcoffset().total_seconds() == 0

    def test_invalid_timezone_falls_back_to_utc(self):
        # Must not raise; result should still be a valid future datetime.
        result = _next_fire("0 * * * *", "Not/AReal_Zone", _NOW)
        assert result > _NOW
        assert result.tzinfo is not None

    def test_named_timezone_accepted(self):
        result = _next_fire("0 * * * *", "America/New_York", _NOW)
        assert result > _NOW
        assert result.tzinfo is not None


# ---------------------------------------------------------------------------
# _try_acquire_lock
# ---------------------------------------------------------------------------


class TestTryAcquireLock:
    def test_returns_true_when_lock_granted(self):
        db = MagicMock()
        db.execute.return_value.scalar.return_value = True
        assert _try_acquire_lock(db, 12345) is True

    def test_returns_false_when_lock_unavailable(self):
        db = MagicMock()
        db.execute.return_value.scalar.return_value = False
        assert _try_acquire_lock(db, 12345) is False


# ---------------------------------------------------------------------------
# _release_lock
# ---------------------------------------------------------------------------


class TestReleaseLock:
    def test_executes_advisory_unlock(self):
        db = MagicMock()
        _release_lock(db, 99)
        db.execute.assert_called_once()
        sql_arg = str(db.execute.call_args[0][0])
        assert "pg_advisory_unlock" in sql_arg


# ---------------------------------------------------------------------------
# _install_signals
# ---------------------------------------------------------------------------


class TestInstallSignals:
    def setup_method(self):
        sched_mod._stop = False

    def teardown_method(self):
        sched_mod._stop = False

    def test_registers_sigint_and_sigterm(self):
        registered = {}

        def capture(sig, handler):
            registered[sig] = handler

        with patch("kiroku.scheduler.runner.signal") as mock_sig:
            mock_sig.SIGINT = signal.SIGINT
            mock_sig.SIGTERM = signal.SIGTERM
            mock_sig.signal.side_effect = capture
            _install_signals()

        assert signal.SIGINT in registered
        assert signal.SIGTERM in registered

    def test_handler_sets_stop_flag(self):
        registered = {}

        def capture(sig, handler):
            registered[sig] = handler

        with patch("kiroku.scheduler.runner.signal") as mock_sig:
            mock_sig.SIGINT = signal.SIGINT
            mock_sig.SIGTERM = signal.SIGTERM
            mock_sig.signal.side_effect = capture
            _install_signals()

        registered[signal.SIGINT](signal.SIGINT, None)
        assert sched_mod._stop is True


# ---------------------------------------------------------------------------
# _fire_due
# ---------------------------------------------------------------------------


class TestFireDue:
    def setup_method(self):
        sched_mod._stop = False

    # ---- no work to do ------------------------------------------------

    def test_no_schedules_returns_zero(self):
        assert _fire_due(make_db([]), _NOW) == 0

    def test_schedule_without_next_run_at_is_initialised(self):
        sched = FakeSchedule(next_run_at=None)
        _fire_due(make_db([sched]), _NOW)
        assert sched.next_run_at is not None
        assert sched.next_run_at > _NOW

    def test_schedule_without_next_run_at_does_not_fire(self):
        sched = FakeSchedule(next_run_at=None)
        with patch("kiroku.scheduler.runner.fire_job") as mock_fire:
            _fire_due(make_db([sched]), _NOW)
        mock_fire.assert_not_called()

    def test_schedule_not_yet_due_is_skipped(self):
        sched = FakeSchedule(next_run_at=_FUTURE)
        with patch("kiroku.scheduler.runner.fire_job") as mock_fire:
            result = _fire_due(make_db([sched]), _NOW)
        assert result == 0
        mock_fire.assert_not_called()

    # ---- skip_next_run ------------------------------------------------

    def test_skip_next_run_does_not_fire_job(self):
        sched = FakeSchedule(next_run_at=_PAST, skip_next_run=True)
        with patch("kiroku.scheduler.runner.fire_job") as mock_fire:
            result = _fire_due(make_db([sched]), _NOW)
        assert result == 0
        mock_fire.assert_not_called()

    def test_skip_next_run_clears_flag(self):
        sched = FakeSchedule(next_run_at=_PAST, skip_next_run=True)
        with patch("kiroku.scheduler.runner.fire_job"):
            _fire_due(make_db([sched]), _NOW)
        assert sched.skip_next_run is False

    def test_skip_next_run_advances_timestamps(self):
        sched = FakeSchedule(next_run_at=_PAST, skip_next_run=True)
        with patch("kiroku.scheduler.runner.fire_job"):
            _fire_due(make_db([sched]), _NOW)
        assert sched.last_run_at == _NOW
        assert sched.next_run_at > _NOW

    # ---- no job attached ----------------------------------------------

    def test_schedule_with_no_job_does_not_fire(self):
        sched = FakeSchedule(next_run_at=_PAST, job=None)
        with patch("kiroku.scheduler.runner.fire_job") as mock_fire:
            result = _fire_due(make_db([sched]), _NOW)
        assert result == 0
        mock_fire.assert_not_called()

    def test_schedule_with_no_job_still_advances(self):
        sched = FakeSchedule(next_run_at=_PAST, job=None)
        with patch("kiroku.scheduler.runner.fire_job"):
            _fire_due(make_db([sched]), _NOW)
        assert sched.last_run_at == _NOW
        assert sched.next_run_at > _NOW

    # ---- successful fire ----------------------------------------------

    def test_successful_fire_returns_queued_count(self):
        sched = FakeSchedule(next_run_at=_PAST, job=FakeJob())
        with patch("kiroku.scheduler.runner.fire_job", return_value=make_batch(3, 0)):
            result = _fire_due(make_db([sched]), _NOW)
        assert result == 3

    def test_successful_fire_updates_timestamps(self):
        sched = FakeSchedule(next_run_at=_PAST, job=FakeJob())
        with patch("kiroku.scheduler.runner.fire_job", return_value=make_batch(1, 0)):
            _fire_due(make_db([sched]), _NOW)
        assert sched.last_run_at == _NOW
        assert sched.next_run_at > _NOW

    def test_fire_job_called_with_correct_args(self):
        job = FakeJob()
        sched = FakeSchedule(id=7, name="my-sched", next_run_at=_PAST, job=job)
        db = make_db([sched])
        with patch("kiroku.scheduler.runner.fire_job", return_value=make_batch()) as mock_fire:
            _fire_due(db, _NOW)
        mock_fire.assert_called_once_with(
            job, db, schedule_id=7, schedule_name="my-sched", commit=False
        )

    def test_all_devices_failed_counts_as_zero_queued(self):
        sched = FakeSchedule(next_run_at=_PAST, job=FakeJob())
        with patch("kiroku.scheduler.runner.fire_job", return_value=make_batch(2, 2)):
            result = _fire_due(make_db([sched]), _NOW)
        assert result == 0

    # ---- fire_job raises ---------------------------------------------

    def test_fire_job_exception_does_not_propagate(self):
        sched = FakeSchedule(next_run_at=_PAST, job=FakeJob())
        with patch("kiroku.scheduler.runner.fire_job", side_effect=RuntimeError("redis down")):
            _fire_due(make_db([sched]), _NOW)  # must not raise

    def test_fire_job_exception_still_advances_next_run_at(self):
        sched = FakeSchedule(next_run_at=_PAST, job=FakeJob())
        with patch("kiroku.scheduler.runner.fire_job", side_effect=RuntimeError("boom")):
            _fire_due(make_db([sched]), _NOW)
        assert sched.next_run_at > _NOW
        assert sched.last_run_at == _NOW

    def test_fire_job_exception_contributes_zero_to_queued(self):
        sched = FakeSchedule(next_run_at=_PAST, job=FakeJob())
        with patch("kiroku.scheduler.runner.fire_job", side_effect=OSError("no redis")):
            result = _fire_due(make_db([sched]), _NOW)
        assert result == 0

    # ---- isolation between schedules ---------------------------------

    def test_failing_schedule_does_not_block_subsequent_ones(self):
        job_a = FakeJob(id=1, name="job-a")
        job_b = FakeJob(id=2, name="job-b")
        job_c = FakeJob(id=3, name="job-c")
        sched_a = FakeSchedule(id=1, name="s-a", next_run_at=_PAST, job=job_a)
        sched_b = FakeSchedule(id=2, name="s-b", next_run_at=_PAST, job=job_b)
        sched_c = FakeSchedule(id=3, name="s-c", next_run_at=_PAST, job=job_c)

        def fire_side_effect(job, db, **kwargs):
            if kwargs["schedule_id"] == 2:
                raise RuntimeError("fail")
            return make_batch(1, 0)

        with patch("kiroku.scheduler.runner.fire_job", side_effect=fire_side_effect):
            result = _fire_due(make_db([sched_a, sched_b, sched_c]), _NOW)

        assert result == 2  # a and c each fired 1 job
        for s in (sched_a, sched_b, sched_c):
            assert s.next_run_at > _NOW

    def test_total_queued_is_summed_across_schedules(self):
        scheds = [
            FakeSchedule(id=i, name=f"s{i}", next_run_at=_PAST, job=FakeJob(id=i, name=f"j{i}"))
            for i in range(1, 4)
        ]
        batches = [make_batch(2, 0), make_batch(3, 1), make_batch(1, 0)]
        with patch("kiroku.scheduler.runner.fire_job", side_effect=batches):
            result = _fire_due(make_db(scheds), _NOW)
        assert result == 2 + 2 + 1  # (2-0) + (3-1) + (1-0)


# ---------------------------------------------------------------------------
# run_scheduler
# ---------------------------------------------------------------------------


class TestRunScheduler:
    """Integration-level tests for the main scheduler loop.

    All external dependencies are patched.  The ``time.sleep`` stub sets
    ``_stop = True`` on its first call so the loop terminates after at most
    one tick without busy-waiting.
    """

    def setup_method(self):
        sched_mod._stop = False

    def teardown_method(self):
        sched_mod._stop = False

    # ------------------------------------------------------------------
    # helpers
    # ------------------------------------------------------------------

    def _make_settings(self, tick_seconds: int = 1):
        s = MagicMock()
        s.scheduler_tick_seconds = tick_seconds
        s.scheduler_advisory_lock_id = 42
        s.job_stream = "kiroku:jobs"
        s.job_consumer_group = "workers"
        s.result_stream = "kiroku:results"
        s.result_consumer_group = "recorders"
        return s

    @contextmanager
    def _run_env(
        self,
        *,
        lock_acquired: bool = True,
        fire_due_return: int = 0,
        fire_due_side_effect=None,
        tick_seconds: int = 1,
    ):
        """Patches all I/O so run_scheduler() completes after one tick."""
        settings = self._make_settings(tick_seconds)
        mock_db = MagicMock()
        mock_release = MagicMock()
        mock_fire = MagicMock(
            return_value=fire_due_return,
            side_effect=fire_due_side_effect,
        )

        def fake_sleep(_n=None):
            sched_mod._stop = True

        @contextmanager
        def fake_scope():
            yield mock_db

        with (
            patch("kiroku.scheduler.runner.configure_logging"),
            patch("kiroku.scheduler.runner._install_signals"),
            patch("kiroku.scheduler.runner.ensure_consumer_group"),
            patch("kiroku.scheduler.runner.get_settings", return_value=settings),
            patch("kiroku.scheduler.runner.session_scope", fake_scope),
            patch("kiroku.scheduler.runner._try_acquire_lock", return_value=lock_acquired),
            patch("kiroku.scheduler.runner._release_lock", mock_release),
            patch("kiroku.scheduler.runner._fire_due", mock_fire),
            patch("kiroku.scheduler.runner.time") as mock_time,
        ):
            mock_time.sleep.side_effect = fake_sleep
            yield {
                "db": mock_db,
                "fire_due": mock_fire,
                "release_lock": mock_release,
                "time": mock_time,
                "settings": settings,
            }

    # ------------------------------------------------------------------
    # tests
    # ------------------------------------------------------------------

    def test_already_stopped_loop_never_executes(self):
        sched_mod._stop = True
        with self._run_env() as env:
            run_scheduler()
        env["fire_due"].assert_not_called()

    def test_already_stopped_lock_never_released(self):
        sched_mod._stop = True
        with self._run_env() as env:
            run_scheduler()
        env["release_lock"].assert_not_called()

    def test_lock_not_acquired_sleeps_with_tick_seconds(self):
        with self._run_env(lock_acquired=False) as env:
            run_scheduler()
        env["time"].sleep.assert_called_with(env["settings"].scheduler_tick_seconds)

    def test_lock_not_acquired_does_not_call_fire_due(self):
        with self._run_env(lock_acquired=False) as env:
            run_scheduler()
        env["fire_due"].assert_not_called()

    def test_lock_acquired_calls_fire_due(self):
        with self._run_env(lock_acquired=True) as env:
            run_scheduler()
        env["fire_due"].assert_called_once()

    def test_fire_due_exception_is_caught(self):
        with self._run_env(fire_due_side_effect=RuntimeError("db gone")) as env:
            run_scheduler()  # must not raise

    def test_queued_nonzero_does_not_raise(self):
        # Exercises the `if queued: log.info("tick complete")` branch.
        with self._run_env(fire_due_return=5):
            run_scheduler()  # no assertion needed; just verify no crash

    def test_lock_released_after_acquiring(self):
        with self._run_env(lock_acquired=True) as env:
            run_scheduler()
        env["release_lock"].assert_called_once()

    def test_lock_not_released_if_never_acquired(self):
        with self._run_env(lock_acquired=False) as env:
            run_scheduler()
        env["release_lock"].assert_not_called()

    def test_inner_sleep_loop_breaks_early_when_stop_set(self):
        """With tick_seconds=3, _stop is set by the first sleep(1), so the
        inner loop should call sleep exactly once rather than three times."""
        sleep_calls = []

        def counting_sleep(_n=None):
            sleep_calls.append(_n)
            sched_mod._stop = True

        settings = self._make_settings(tick_seconds=3)
        mock_db = MagicMock()

        @contextmanager
        def fake_scope():
            yield mock_db

        with (
            patch("kiroku.scheduler.runner.configure_logging"),
            patch("kiroku.scheduler.runner._install_signals"),
            patch("kiroku.scheduler.runner.ensure_consumer_group"),
            patch("kiroku.scheduler.runner.get_settings", return_value=settings),
            patch("kiroku.scheduler.runner.session_scope", fake_scope),
            patch("kiroku.scheduler.runner._try_acquire_lock", return_value=True),
            patch("kiroku.scheduler.runner._release_lock"),
            patch("kiroku.scheduler.runner._fire_due", return_value=0),
            patch("kiroku.scheduler.runner.time") as mock_time,
        ):
            mock_time.sleep.side_effect = counting_sleep
            run_scheduler()

        # Only one time.sleep(1) call from the inner loop (not three).
        assert sleep_calls == [1]
