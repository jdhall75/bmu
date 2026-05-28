"""Tests for kiroku.worker.runner."""

from __future__ import annotations

import signal
from unittest.mock import MagicMock, call, patch

import pytest

import kiroku.worker.runner as runner_mod
from kiroku.jobs import EmbeddedCredential, JobResult, JobSpec
from kiroku.worker.runner import _handle, _install_signals


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_spec(*, has_credential: bool = True, run_id: int = 1) -> JobSpec:
    cred_ref = MagicMock()
    cred_ref.provider = "local"
    cred_ref.credential_id = 1
    cred_ref.ref = None

    spec = MagicMock(spec=JobSpec)
    spec.run_id = run_id
    spec.device_id = 10
    spec.device_name = "router1"
    spec.kind = "backup"
    spec.credential = cred_ref

    if has_credential:
        cred = MagicMock(spec=EmbeddedCredential)
        cred.username = "admin"
        cred.password = "secret"
        cred.enable_password = None
        cred.private_key = None
        cred.private_key_passphrase = None
        spec.credential_material = cred
    else:
        spec.credential_material = None

    return spec


# ---------------------------------------------------------------------------
# _install_signals
# ---------------------------------------------------------------------------


class TestInstallSignals:
    def test_registers_sigint_and_sigterm(self):
        with patch("kiroku.worker.runner.signal") as mock_signal:
            _install_signals()
        assert mock_signal.signal.call_count == 2
        registered = [c[0][0] for c in mock_signal.signal.call_args_list]
        assert mock_signal.SIGINT in registered
        assert mock_signal.SIGTERM in registered

    def test_handler_sets_stop_flag(self):
        runner_mod._stop = False
        _install_signals()
        # Trigger SIGINT handler directly via signal.getsignal
        handler = signal.getsignal(signal.SIGINT)
        handler(signal.SIGINT, None)
        assert runner_mod._stop is True
        # Reset
        runner_mod._stop = False


# ---------------------------------------------------------------------------
# _handle — missing credential_material
# ---------------------------------------------------------------------------


class TestHandleMissingCredential:
    def test_publishes_failure_result_when_no_credential(self):
        spec = _make_spec(has_credential=False)
        with patch("kiroku.worker.runner.publish_result") as mock_pub, \
             patch("kiroku.worker.runner.ack_job") as mock_ack:
            _handle("1-0", spec)
        mock_pub.assert_called_once()
        result: JobResult = mock_pub.call_args[0][0]
        assert result.success is False
        assert "credential_material" in result.error

    def test_acks_job_even_when_no_credential(self):
        spec = _make_spec(has_credential=False)
        with patch("kiroku.worker.runner.publish_result"), \
             patch("kiroku.worker.runner.ack_job") as mock_ack:
            _handle("1-0", spec)
        mock_ack.assert_called_once_with("1-0")

    def test_returns_early_without_calling_execute(self):
        spec = _make_spec(has_credential=False)
        with patch("kiroku.worker.runner.publish_result"), \
             patch("kiroku.worker.runner.ack_job"), \
             patch("kiroku.worker.runner.execute") as mock_exec:
            _handle("1-0", spec)
        mock_exec.assert_not_called()


# ---------------------------------------------------------------------------
# _handle — successful execution
# ---------------------------------------------------------------------------


class TestHandleSuccess:
    def test_calls_execute_with_spec_and_material(self):
        spec = _make_spec()
        mock_result = MagicMock(spec=JobResult)
        mock_result.success = True
        with patch("kiroku.worker.runner.execute", return_value=mock_result) as mock_exec, \
             patch("kiroku.worker.runner.publish_result"), \
             patch("kiroku.worker.runner.ack_job"):
            _handle("2-0", spec)
        mock_exec.assert_called_once()

    def test_publishes_result_and_acks(self):
        spec = _make_spec()
        mock_result = MagicMock(spec=JobResult)
        mock_result.success = True
        with patch("kiroku.worker.runner.execute", return_value=mock_result), \
             patch("kiroku.worker.runner.publish_result") as mock_pub, \
             patch("kiroku.worker.runner.ack_job") as mock_ack:
            _handle("2-0", spec)
        mock_pub.assert_called_once_with(mock_result)
        mock_ack.assert_called_once_with("2-0")

    def test_credential_material_fields_passed_to_execute(self):
        spec = _make_spec()
        mock_result = MagicMock(spec=JobResult)
        mock_result.success = True
        captured = {}
        def fake_execute(s, material):
            captured["material"] = material
            return mock_result
        with patch("kiroku.worker.runner.execute", side_effect=fake_execute), \
             patch("kiroku.worker.runner.publish_result"), \
             patch("kiroku.worker.runner.ack_job"):
            _handle("2-0", spec)
        assert captured["material"].username == "admin"
        assert captured["material"].password == "secret"


# ---------------------------------------------------------------------------
# _handle — execute raises an exception
# ---------------------------------------------------------------------------


class TestHandleExecuteException:
    def test_publishes_failure_result_on_exception(self):
        spec = _make_spec()
        with patch("kiroku.worker.runner.execute", side_effect=RuntimeError("boom")), \
             patch("kiroku.worker.runner.publish_result") as mock_pub, \
             patch("kiroku.worker.runner.ack_job"):
            _handle("3-0", spec)
        result: JobResult = mock_pub.call_args[0][0]
        assert result.success is False
        assert "RuntimeError" in result.error
        assert "boom" in result.error

    def test_still_acks_after_exception(self):
        spec = _make_spec()
        with patch("kiroku.worker.runner.execute", side_effect=ValueError("oops")), \
             patch("kiroku.worker.runner.publish_result"), \
             patch("kiroku.worker.runner.ack_job") as mock_ack:
            _handle("3-0", spec)
        mock_ack.assert_called_once_with("3-0")

    def test_traceback_included_in_error(self):
        spec = _make_spec()
        with patch("kiroku.worker.runner.execute", side_effect=Exception("crash")), \
             patch("kiroku.worker.runner.publish_result") as mock_pub, \
             patch("kiroku.worker.runner.ack_job"):
            _handle("3-0", spec)
        result: JobResult = mock_pub.call_args[0][0]
        assert "Traceback" in result.error or "crash" in result.error


# ---------------------------------------------------------------------------
# run_worker loop
# ---------------------------------------------------------------------------


class TestRunWorker:
    def _make_settings(self):
        s = MagicMock()
        s.worker_concurrency = 2
        return s

    def test_loop_exits_when_stop_set(self):
        runner_mod._stop = False
        spec = _make_spec()
        mock_result = MagicMock(spec=JobResult)
        mock_result.success = True

        call_count = 0
        def fake_read_jobs(consumer, *, count, block_ms):
            nonlocal call_count
            call_count += 1
            runner_mod._stop = True
            return []

        with patch("kiroku.worker.runner.configure_logging"), \
             patch("kiroku.worker.runner.get_settings", return_value=self._make_settings()), \
             patch("kiroku.worker.runner._install_signals"), \
             patch("kiroku.worker.runner.read_jobs", side_effect=fake_read_jobs), \
             patch("kiroku.worker.runner.ProcessPoolExecutor") as mock_pool_cls:
            mock_pool = MagicMock()
            mock_pool.__enter__ = MagicMock(return_value=mock_pool)
            mock_pool.__exit__ = MagicMock(return_value=False)
            mock_pool_cls.return_value = mock_pool
            from kiroku.worker.runner import run_worker
            run_worker()

        assert call_count == 1

    def test_read_jobs_exception_continues_loop(self):
        runner_mod._stop = False
        call_count = 0

        def fake_read_jobs(consumer, *, count, block_ms):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise ConnectionError("redis down")
            runner_mod._stop = True
            return []

        with patch("kiroku.worker.runner.configure_logging"), \
             patch("kiroku.worker.runner.get_settings", return_value=self._make_settings()), \
             patch("kiroku.worker.runner._install_signals"), \
             patch("kiroku.worker.runner.read_jobs", side_effect=fake_read_jobs), \
             patch("kiroku.worker.runner.ProcessPoolExecutor") as mock_pool_cls:
            mock_pool = MagicMock()
            mock_pool.__enter__ = MagicMock(return_value=mock_pool)
            mock_pool.__exit__ = MagicMock(return_value=False)
            mock_pool_cls.return_value = mock_pool
            from kiroku.worker.runner import run_worker
            run_worker()

        assert call_count == 2

    def test_jobs_are_submitted_to_pool(self):
        runner_mod._stop = False
        spec = _make_spec()
        call_count = 0

        def fake_read_jobs(consumer, *, count, block_ms):
            nonlocal call_count
            call_count += 1
            runner_mod._stop = True
            return [("1-0", spec)]

        with patch("kiroku.worker.runner.configure_logging"), \
             patch("kiroku.worker.runner.get_settings", return_value=self._make_settings()), \
             patch("kiroku.worker.runner._install_signals"), \
             patch("kiroku.worker.runner.read_jobs", side_effect=fake_read_jobs), \
             patch("kiroku.worker.runner.ProcessPoolExecutor") as mock_pool_cls:
            mock_pool = MagicMock()
            mock_pool.__enter__ = MagicMock(return_value=mock_pool)
            mock_pool.__exit__ = MagicMock(return_value=False)
            mock_future = MagicMock()
            mock_pool.submit.return_value = mock_future
            mock_pool_cls.return_value = mock_pool
            from kiroku.worker.runner import run_worker
            run_worker()

        mock_pool.submit.assert_called_once()
        submit_args = mock_pool.submit.call_args[0]
        assert submit_args[1] == "1-0"
        assert submit_args[2] is spec
