"""Tests for kiroku.worker.scrapli_runner.

All network I/O is patched; no real connections are made.
"""
from unittest.mock import MagicMock, patch

import pytest

from kiroku.worker.scrapli_runner import _build_cli_driver, _run_cli, _run_netconf, execute

from .conftest import make_cred, make_driver, make_spec, mock_response

# ---------------------------------------------------------------------------
# _build_cli_driver
# ---------------------------------------------------------------------------


class TestBuildCliDriver:
    """Verify the Cli driver is constructed with the right options."""

    def _build(self, spec, cred=None, mock_settings=None):
        if cred is None:
            cred = make_cred()
        ctx = patch("kiroku.worker.scrapli_runner.get_settings", return_value=mock_settings)
        with ctx, patch("kiroku.worker.scrapli_runner.Cli") as MockCli:
            MockCli.return_value = MagicMock()
            driver, temp = _build_cli_driver(spec, cred)
            return MockCli, driver, temp

    # ---- platform / definition selection -----------------------------------

    def test_named_platform_passed_as_definition(self, mock_settings):
        spec = make_spec(platform="cisco_iosxe")
        MockCli, _, _ = self._build(spec, mock_settings=mock_settings)
        assert MockCli.call_args.kwargs["definition_file_or_name"] == "cisco_iosxe"

    def test_platform_name_is_lowercased(self, mock_settings):
        spec = make_spec(platform="Cisco_IosXE")
        MockCli, _, _ = self._build(spec, mock_settings=mock_settings)
        assert MockCli.call_args.kwargs["definition_file_or_name"] == "cisco_iosxe"

    def test_generic_platform_writes_temp_definition(self, mock_settings):
        spec = make_spec(platform="generic")
        MockCli, _, temp = self._build(spec, mock_settings=mock_settings)
        # A temp file path is returned so the caller can delete it after open()
        assert temp is not None
        # The definition passed to Cli is the temp file path
        assert MockCli.call_args.kwargs["definition_file_or_name"] == temp

    def test_none_platform_also_writes_temp_definition(self, mock_settings):
        spec = make_spec(platform=None)
        MockCli, _, temp = self._build(spec, mock_settings=mock_settings)
        assert temp is not None

    def test_custom_platform_yaml_writes_tempfile(self, mock_settings):
        yaml = 'prompt_pattern: "^.*[#>]"\ndefault_mode: "exec"\nmodes: []'
        spec = make_spec(platform=None, custom_platform_yaml=yaml)
        MockCli, _, temp = self._build(spec, mock_settings=mock_settings)
        assert temp is not None
        content = open(temp).read()
        assert "prompt_pattern" in content
        definition = MockCli.call_args.kwargs["definition_file_or_name"]
        assert definition == temp
        import os; os.unlink(temp)

    def test_generic_with_prompt_pattern_writes_it_into_yaml(self, mock_settings, tmp_path):
        spec = make_spec(platform="generic", prompt_pattern=r"^.*[#>]\s*$")
        with patch("kiroku.worker.scrapli_runner.get_settings", return_value=mock_settings), \
             patch("kiroku.worker.scrapli_runner.Cli") as MockCli:
            MockCli.return_value = MagicMock()
            _, temp = _build_cli_driver(spec, make_cred())
        assert temp is not None
        content = open(temp).read()
        assert r"^.*[#>]\s*$" in content
        import os; os.unlink(temp)

    def test_generic_without_prompt_pattern_uses_default(self, mock_settings):
        spec = make_spec(platform="generic", prompt_pattern=None)
        with patch("kiroku.worker.scrapli_runner.get_settings", return_value=mock_settings), \
             patch("kiroku.worker.scrapli_runner.Cli") as MockCli:
            MockCli.return_value = MagicMock()
            _, temp = _build_cli_driver(spec, make_cred())
        assert temp is not None
        content = open(temp).read()
        assert "prompt_pattern" in content
        import os; os.unlink(temp)

    # ---- transport ---------------------------------------------------------

    def test_ssh_transport_uses_bin_options(self, mock_settings):
        from scrapli import TransportBinOptions
        spec = make_spec(platform="cisco_iosxe", transport="ssh")
        MockCli, _, _ = self._build(spec, mock_settings=mock_settings)
        opts = MockCli.call_args.kwargs["transport_options"]
        assert isinstance(opts, TransportBinOptions)

    def test_none_transport_uses_bin_options(self, mock_settings):
        from scrapli import TransportBinOptions
        spec = make_spec(platform="cisco_iosxe", transport=None)
        MockCli, _, _ = self._build(spec, mock_settings=mock_settings)
        assert isinstance(MockCli.call_args.kwargs["transport_options"], TransportBinOptions)

    def test_telnet_transport_uses_telnet_options(self, mock_settings):
        from scrapli import TransportTelnetOptions
        spec = make_spec(platform="cisco_iosxe", transport="telnet")
        MockCli, _, _ = self._build(spec, mock_settings=mock_settings)
        assert isinstance(MockCli.call_args.kwargs["transport_options"], TransportTelnetOptions)

    def test_bin_transport_disables_strict_key(self, mock_settings):
        spec = make_spec(platform="cisco_iosxe", transport="ssh")
        MockCli, _, _ = self._build(spec, mock_settings=mock_settings)
        opts = MockCli.call_args.kwargs["transport_options"]
        assert opts.enable_strict_key is False

    # ---- connection params -------------------------------------------------

    def test_host_set_from_spec(self, mock_settings):
        spec = make_spec(platform="cisco_iosxe", hostname="10.0.0.99")
        MockCli, _, _ = self._build(spec, mock_settings=mock_settings)
        assert MockCli.call_args.kwargs["host"] == "10.0.0.99"

    def test_port_from_spec(self, mock_settings):
        spec = make_spec(platform="cisco_iosxe", port=2222)
        MockCli, _, _ = self._build(spec, mock_settings=mock_settings)
        assert MockCli.call_args.kwargs["port"] == 2222

    def test_port_defaults_to_22_for_ssh(self, mock_settings):
        spec = make_spec(platform="cisco_iosxe", port=None, transport="ssh")
        MockCli, _, _ = self._build(spec, mock_settings=mock_settings)
        assert MockCli.call_args.kwargs["port"] == 22

    def test_port_defaults_to_23_for_telnet(self, mock_settings):
        spec = make_spec(platform="cisco_iosxe", port=None, transport="telnet")
        MockCli, _, _ = self._build(spec, mock_settings=mock_settings)
        assert MockCli.call_args.kwargs["port"] == 23

    # ---- auth options ------------------------------------------------------

    def test_credentials_in_auth_options(self, mock_settings):
        from scrapli import AuthOptions
        spec = make_spec(platform="cisco_iosxe")
        cred = make_cred(username="netops", password="p@ss")
        MockCli, _, _ = self._build(spec, cred=cred, mock_settings=mock_settings)
        auth = MockCli.call_args.kwargs["auth_options"]
        assert isinstance(auth, AuthOptions)
        assert auth.username == "netops"
        assert auth.password == "p@ss"

    def test_enable_password_added_as_lookup(self, mock_settings):
        spec = make_spec(platform="cisco_iosxe")
        cred = make_cred(enable_password="en@ble")
        MockCli, _, _ = self._build(spec, cred=cred, mock_settings=mock_settings)
        auth = MockCli.call_args.kwargs["auth_options"]
        assert auth.lookups is not None
        assert auth.lookups[0].key == "enable"
        assert auth.lookups[0].value == "en@ble"

    def test_no_enable_password_lookups_is_none(self, mock_settings):
        spec = make_spec(platform="cisco_iosxe")
        cred = make_cred(enable_password=None)
        MockCli, _, _ = self._build(spec, cred=cred, mock_settings=mock_settings)
        auth = MockCli.call_args.kwargs["auth_options"]
        assert auth.lookups is None

    def test_private_key_in_auth_options(self, mock_settings):
        spec = make_spec(platform="cisco_iosxe")
        cred = make_cred(private_key="/home/user/.ssh/id_rsa")
        MockCli, _, _ = self._build(spec, cred=cred, mock_settings=mock_settings)
        auth = MockCli.call_args.kwargs["auth_options"]
        assert auth.private_key_path == "/home/user/.ssh/id_rsa"

    def test_no_private_key_is_none(self, mock_settings):
        spec = make_spec(platform="cisco_iosxe")
        cred = make_cred(private_key=None)
        MockCli, _, _ = self._build(spec, cred=cred, mock_settings=mock_settings)
        auth = MockCli.call_args.kwargs["auth_options"]
        assert auth.private_key_path is None

    # ---- session / timeout -------------------------------------------------

    def test_command_timeout_in_session_options(self, mock_settings):
        from scrapli import SessionOptions
        mock_settings.worker_command_timeout = 45
        spec = make_spec(platform="cisco_iosxe")
        MockCli, _, _ = self._build(spec, mock_settings=mock_settings)
        session = MockCli.call_args.kwargs["session_options"]
        assert isinstance(session, SessionOptions)
        assert session.operation_timeout_s == 45


# ---------------------------------------------------------------------------
# _run_cli
# ---------------------------------------------------------------------------


class TestRunCli:
    """Tests for the CLI execution path. _build_cli_driver is always patched."""

    def _run(self, spec, cred=None, driver=None):
        if cred is None:
            cred = make_cred()
        if driver is None:
            driver = make_driver()
        with patch("kiroku.worker.scrapli_runner._build_cli_driver", return_value=(driver, None)):
            return _run_cli(spec, cred)

    # ---- backup mode -------------------------------------------------------

    def test_backup_config_text_populated(self):
        driver = make_driver(mock_response("version 15.2"))
        spec = make_spec(kind="backup", commands=["show version"])
        result = self._run(spec, driver=driver)
        assert result.config_text == "version 15.2"

    def test_backup_multiple_commands_joined_with_newline(self):
        driver = make_driver(mock_response("part1"), mock_response("part2"))
        spec = make_spec(kind="backup", commands=["show run", "show version"])
        result = self._run(spec, driver=driver)
        assert result.config_text == "part1\npart2"

    def test_backup_does_not_call_parser(self):
        spec = make_spec(kind="backup", commands=["show run"])
        with patch("kiroku.worker.scrapli_runner.parse") as mock_parse, \
             patch("kiroku.worker.scrapli_runner._build_cli_driver", return_value=(make_driver(), None)):
            _run_cli(spec, make_cred())
            mock_parse.assert_not_called()

    # ---- collect mode ------------------------------------------------------

    def test_collect_config_text_is_none(self):
        spec = make_spec(kind="collect", commands=["show ip int brief"])
        result = self._run(spec)
        assert result.config_text is None

    def test_collect_populates_command_results(self):
        driver = make_driver(mock_response("10.0.0.1  up"))
        spec = make_spec(kind="collect", commands=["show ip int brief"])
        result = self._run(spec, driver=driver)
        assert len(result.command_results) == 1
        assert result.command_results[0].command == "show ip int brief"
        assert result.command_results[0].output == "10.0.0.1  up"

    def test_collect_with_parser_calls_parse(self):
        spec = make_spec(
            kind="collect",
            commands=["show version"],
            parser_type="textfsm",
            parser_body="Value X (.*)\n\nStart\n  ^${X} -> Record\n\nEOF",
        )
        with patch("kiroku.worker.scrapli_runner.parse", return_value=[{"X": "val"}]) as mock_parse, \
             patch("kiroku.worker.scrapli_runner._build_cli_driver",
                   return_value=(make_driver(mock_response("val")), None)):
            result = _run_cli(spec, make_cred())
            mock_parse.assert_called_once_with("textfsm", spec.parser_body, "val")
            assert result.parsed == [{"X": "val"}]

    def test_collect_parser_exception_does_not_propagate(self):
        spec = make_spec(
            kind="collect",
            commands=["show version"],
            parser_type="textfsm",
            parser_body="bad template",
        )
        with patch("kiroku.worker.scrapli_runner.parse", side_effect=Exception("parse error")), \
             patch("kiroku.worker.scrapli_runner._build_cli_driver", return_value=(make_driver(), None)):
            result = _run_cli(spec, make_cred())
            assert result.success is True
            assert result.parsed is None

    def test_collect_no_parser_type_skips_parse(self):
        spec = make_spec(kind="collect", commands=["show version"], parser_type=None)
        with patch("kiroku.worker.scrapli_runner.parse") as mock_parse, \
             patch("kiroku.worker.scrapli_runner._build_cli_driver", return_value=(make_driver(), None)):
            _run_cli(spec, make_cred())
            mock_parse.assert_not_called()

    # ---- command sequencing ------------------------------------------------

    def test_pre_commands_sent_before_commands(self):
        driver = make_driver(
            mock_response(),           # enable
            mock_response(),           # terminal length 0
            mock_response("config"),   # show run
        )
        spec = make_spec(
            pre_commands=["enable"],
            disable_paging_command="terminal length 0",
            commands=["show run"],
        )
        self._run(spec, driver=driver)
        sent = [c.kwargs["input_"] for c in driver.send_input.call_args_list]
        assert sent == ["enable", "terminal length 0", "show run"]

    def test_multiple_pre_commands_all_sent(self):
        driver = make_driver(*[mock_response() for _ in range(4)])
        spec = make_spec(
            pre_commands=["enable", "conf t"],
            disable_paging_command=None,
            commands=["show run"],
        )
        self._run(spec, driver=driver)
        sent = [c.kwargs["input_"] for c in driver.send_input.call_args_list]
        assert sent == ["enable", "conf t", "show run"]

    def test_no_pre_commands_skips_pre_phase(self):
        driver = make_driver(mock_response("output"))
        spec = make_spec(pre_commands=[], disable_paging_command=None, commands=["show run"])
        self._run(spec, driver=driver)
        assert driver.send_input.call_count == 1
        assert driver.send_input.call_args.kwargs["input_"] == "show run"

    def test_no_disable_paging_skips_that_call(self):
        driver = make_driver(mock_response("pre"), mock_response("cmd"))
        spec = make_spec(
            pre_commands=["enable"],
            disable_paging_command=None,
            commands=["show run"],
        )
        self._run(spec, driver=driver)
        sent = [c.kwargs["input_"] for c in driver.send_input.call_args_list]
        assert sent == ["enable", "show run"]

    def test_multiple_commands_all_run(self):
        driver = make_driver(mock_response("a"), mock_response("b"), mock_response("c"))
        spec = make_spec(commands=["cmd1", "cmd2", "cmd3"])
        result = self._run(spec, driver=driver)
        assert len(result.command_results) == 3
        assert [r.command for r in result.command_results] == ["cmd1", "cmd2", "cmd3"]

    # ---- success/failure ---------------------------------------------------

    def test_all_commands_succeed_sets_success_true(self):
        spec = make_spec(commands=["show run"])
        result = self._run(spec, driver=make_driver(mock_response(failed=False)))
        assert result.success is True
        assert result.error is None

    def test_failed_command_sets_success_false(self):
        driver = make_driver(mock_response(failed=True))
        spec = make_spec(commands=["bad command"])
        result = self._run(spec, driver=driver)
        assert result.success is False

    def test_any_failed_command_sets_success_false(self):
        driver = make_driver(mock_response(failed=False), mock_response(failed=True))
        spec = make_spec(commands=["ok", "bad"])
        result = self._run(spec, driver=driver)
        assert result.success is False

    def test_open_exception_sets_error_and_success_false(self):
        driver = make_driver()
        driver.open.side_effect = ConnectionError("refused")
        spec = make_spec(commands=["show run"])
        result = self._run(spec, driver=driver)
        assert result.success is False
        assert "ConnectionError" in result.error
        assert "refused" in result.error

    # ---- driver lifecycle --------------------------------------------------

    def test_driver_open_called(self):
        driver = make_driver()
        self._run(make_spec(), driver=driver)
        driver.open.assert_called_once()

    def test_driver_close_called_on_success(self):
        driver = make_driver()
        self._run(make_spec(), driver=driver)
        driver.close.assert_called_once()

    def test_driver_close_called_even_when_command_raises(self):
        driver = make_driver()
        driver.send_input.side_effect = RuntimeError("timeout")
        self._run(make_spec(), driver=driver)
        driver.close.assert_called_once()

    # ---- result fields -----------------------------------------------------

    def test_result_preserves_run_id_and_device_fields(self):
        spec = make_spec(run_id=42, device_id=99, device_name="core-rtr-01", kind="backup")
        result = self._run(spec)
        assert result.run_id == 42
        assert result.device_id == 99
        assert result.device_name == "core-rtr-01"
        assert result.kind == "backup"

    def test_result_timestamps_are_set(self):
        result = self._run(make_spec())
        assert result.started_at
        assert result.finished_at

    def test_command_result_elapsed_ms_is_non_negative_int(self):
        result = self._run(make_spec(commands=["show run"]))
        assert isinstance(result.command_results[0].elapsed_ms, int)
        assert result.command_results[0].elapsed_ms >= 0


# ---------------------------------------------------------------------------
# _run_netconf
# ---------------------------------------------------------------------------


class TestRunNetconf:
    """Tests for the NETCONF execution path."""

    def _make_netconf_driver(self, rpc_result="<data/>", rpc_failed=False):
        driver = MagicMock()
        resp = MagicMock()
        resp.result = rpc_result
        resp.failed = rpc_failed
        driver.raw_rpc.return_value = resp
        return driver

    def _run(self, spec, driver=None):
        if driver is None:
            driver = self._make_netconf_driver()
        with patch("kiroku.worker.scrapli_runner.Netconf", return_value=driver), \
             patch("kiroku.worker.scrapli_runner.get_settings") as mock_gs:
            mock_gs.return_value = MagicMock(worker_command_timeout=60)
            return _run_netconf(spec, make_cred())

    def _netconf_spec(self, **kwargs):
        defaults = dict(
            run_id=1,
            device_id=10,
            device_name="netconf-device",
            hostname="10.0.0.1",
            port=830,
            kind="backup",
            profile_id=2,
            profile_kind="netconf",
            rpc="<get-config/>",
            credential=CredentialRef(provider="local", credential_id=1),
        )
        from kiroku.jobs import JobSpec
        return JobSpec(**{**defaults, **kwargs})

    def test_backup_config_text_is_raw_xml(self):
        spec = self._netconf_spec(kind="backup")
        driver = self._make_netconf_driver(rpc_result="<config>data</config>")
        result = self._run(spec, driver=driver)
        assert result.config_text == "<config>data</config>"
        assert result.success is True

    def test_collect_config_text_is_none(self):
        spec = self._netconf_spec(kind="collect")
        result = self._run(spec)
        assert result.config_text is None

    def test_missing_rpc_sets_error(self):
        spec = self._netconf_spec(rpc=None)
        result = self._run(spec)
        assert result.success is False
        assert "netconf profile is missing rpc" in result.error

    def test_open_exception_sets_error(self):
        driver = self._make_netconf_driver()
        driver.open.side_effect = ConnectionRefusedError("port closed")
        result = self._run(make_spec(profile_kind="netconf", rpc="<get/>"), driver=driver)
        assert result.success is False
        assert "ConnectionRefusedError" in result.error

    def test_driver_close_called_on_success(self):
        spec = self._netconf_spec()
        driver = self._make_netconf_driver()
        self._run(spec, driver=driver)
        driver.close.assert_called_once()

    def test_driver_close_called_on_exception(self):
        spec = self._netconf_spec()
        driver = self._make_netconf_driver()
        driver.raw_rpc.side_effect = TimeoutError("ops timeout")
        self._run(spec, driver=driver)
        driver.close.assert_called_once()

    def test_netconf_driver_constructed_with_correct_args(self):
        from scrapli import AuthOptions, SessionOptions, TransportBinOptions
        spec = self._netconf_spec(hostname="10.1.2.3", port=830)
        with patch("kiroku.worker.scrapli_runner.Netconf") as MockNetconf, \
             patch("kiroku.worker.scrapli_runner.get_settings") as mock_gs:
            mock_gs.return_value = MagicMock(worker_command_timeout=20)
            MockNetconf.return_value = self._make_netconf_driver()
            _run_netconf(spec, make_cred(username="ops", password="pw"))
            kw = MockNetconf.call_args.kwargs
            assert kw["host"] == "10.1.2.3"
            assert kw["port"] == 830
            assert isinstance(kw["auth_options"], AuthOptions)
            assert kw["auth_options"].username == "ops"
            assert kw["auth_options"].password == "pw"
            assert isinstance(kw["transport_options"], TransportBinOptions)
            assert kw["transport_options"].enable_strict_key is False
            assert isinstance(kw["session_options"], SessionOptions)
            assert kw["session_options"].operation_timeout_s == 20

    def test_netconf_port_defaults_to_830(self):
        spec = self._netconf_spec(port=None)
        with patch("kiroku.worker.scrapli_runner.Netconf") as MockNetconf, \
             patch("kiroku.worker.scrapli_runner.get_settings") as mock_gs:
            mock_gs.return_value = MagicMock(worker_command_timeout=60)
            MockNetconf.return_value = self._make_netconf_driver()
            _run_netconf(spec, make_cred())
            assert MockNetconf.call_args.kwargs["port"] == 830

    def test_rpc_sent_as_keyword_arg(self):
        spec = self._netconf_spec(rpc="<custom-rpc/>")
        driver = self._make_netconf_driver()
        self._run(spec, driver=driver)
        driver.raw_rpc.assert_called_once_with(rpc="<custom-rpc/>")

    def test_with_parser_calls_parse(self):
        spec = self._netconf_spec(
            kind="collect",
            rpc="<get-config/>",
            parser_type="xslt",
            parser_body="<xsl:stylesheet/>",
        )
        driver = self._make_netconf_driver(rpc_result="<data/>")
        with patch("kiroku.worker.scrapli_runner.Netconf", return_value=driver), \
             patch("kiroku.worker.scrapli_runner.get_settings") as mock_gs, \
             patch("kiroku.worker.scrapli_runner.parse", return_value={"transformed": ""}) as mock_parse:
            mock_gs.return_value = MagicMock(worker_command_timeout=60)
            result = _run_netconf(spec, make_cred())
            mock_parse.assert_called_once_with("xslt", "<xsl:stylesheet/>", "<data/>")
            assert result.parsed == {"transformed": ""}

    def test_result_preserves_run_id_and_device_fields(self):
        spec = self._netconf_spec(run_id=7, device_id=3, device_name="nconf-rtr")
        result = self._run(spec)
        assert result.run_id == 7
        assert result.device_id == 3
        assert result.device_name == "nconf-rtr"

    def test_command_results_always_empty_list(self):
        result = self._run(self._netconf_spec())
        assert result.command_results == []


# ---------------------------------------------------------------------------
# execute (dispatcher)
# ---------------------------------------------------------------------------


class TestExecute:
    def test_cli_profile_kind_dispatches_to_run_cli(self):
        spec = make_spec(profile_kind="cli")
        with patch("kiroku.worker.scrapli_runner._run_cli") as mock_cli:
            execute(spec, make_cred())
            mock_cli.assert_called_once_with(spec, make_cred())

    def test_netconf_profile_kind_dispatches_to_run_netconf(self):
        spec = make_spec(profile_kind="netconf")
        with patch("kiroku.worker.scrapli_runner._run_netconf") as mock_nc:
            execute(spec, make_cred())
            mock_nc.assert_called_once_with(spec, make_cred())

    def test_unknown_profile_kind_raises_value_error(self):
        spec = make_spec(profile_kind="cli")
        object.__setattr__(spec, "profile_kind", "grpc")  # bypass pydantic literal
        with pytest.raises(ValueError, match="unknown profile kind"):
            execute(spec, make_cred())


# ---------------------------------------------------------------------------
# Import needed for netconf spec
# ---------------------------------------------------------------------------
from kiroku.jobs import CredentialRef  # noqa: E402
