from __future__ import annotations

from io import StringIO, TextIOWrapper
import os
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

import mycli.client as client_module
from mycli.client import MyCli


def write_myclirc(tmp_path: Path, content: str) -> str:
    myclirc = tmp_path / 'myclirc'
    myclirc.write_text(content, encoding='utf-8')
    return str(myclirc)


def patch_constructor_side_effects(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(MyCli, 'system_config_files', [])
    monkeypatch.setattr(MyCli, 'pwd_config_file', os.devnull)
    monkeypatch.setattr(MyCli, 'initialize_logging', lambda self: None)
    monkeypatch.setattr(MyCli, 'register_special_commands', lambda self: None)
    monkeypatch.setattr(client_module, 'get_mylogin_cnf_path', lambda: None)


def test_init_reports_invalid_ssl_mode(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    patch_constructor_side_effects(monkeypatch)
    echo_calls: list[tuple[str, dict[str, Any]]] = []
    monkeypatch.setattr(MyCli, 'echo', lambda self, message, **kwargs: echo_calls.append((message, kwargs)))
    myclirc = write_myclirc(
        tmp_path,
        """
        [main]
        ssl_mode = invalid
        """,
    )

    cli = MyCli(myclirc=myclirc)

    assert cli.ssl_mode is None
    assert echo_calls == [('Invalid config option provided for ssl_mode (invalid); ignoring.', {'err': True, 'fg': 'red'})]


def test_init_uses_defaults_file_for_mysql_config_files(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    patch_constructor_side_effects(monkeypatch)
    defaults_file = tmp_path / 'defaults.cnf'
    defaults_file.write_text('[client]\nuser = alice\n', encoding='utf-8')
    myclirc = write_myclirc(tmp_path, '')

    cli = MyCli(defaults_file=str(defaults_file), myclirc=myclirc)

    assert cli.cnf_files == [str(defaults_file)]


def test_init_honors_explicit_show_warnings(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    patch_constructor_side_effects(monkeypatch)
    show_warnings_calls: list[bool] = []
    monkeypatch.setattr(client_module.special, 'set_show_warnings_enabled', lambda value: show_warnings_calls.append(value))
    myclirc = write_myclirc(tmp_path, '')

    MyCli(myclirc=myclirc, show_warnings=True)

    assert show_warnings_calls == [True]


def test_init_uses_cli_verbosity_override(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    patch_constructor_side_effects(monkeypatch)
    myclirc = write_myclirc(tmp_path, '')

    cli = MyCli(myclirc=myclirc, cli_verbosity=2)

    assert cli.verbosity == 2


def test_init_writes_default_config_when_user_config_is_missing(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    patch_constructor_side_effects(monkeypatch)
    write_calls: list[str] = []
    myclirc = tmp_path / 'missing-myclirc'
    monkeypatch.setattr(client_module, 'write_default_config', lambda destination: write_calls.append(destination))

    MyCli(myclirc=str(myclirc))

    assert write_calls == [str(myclirc)]


def test_init_opens_audit_log_from_config(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    patch_constructor_side_effects(monkeypatch)
    audit_log = tmp_path / 'audit.log'
    myclirc = write_myclirc(
        tmp_path,
        f"""
        [main]
        audit_log = {audit_log}
        """,
    )

    cli = MyCli(myclirc=myclirc)
    try:
        assert isinstance(cli.logfile, TextIOWrapper)
        assert Path(cli.logfile.name) == audit_log
    finally:
        if isinstance(cli.logfile, TextIOWrapper):
            cli.logfile.close()


def test_init_disables_audit_log_when_file_cannot_be_opened(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    patch_constructor_side_effects(monkeypatch)
    echo_calls: list[tuple[str, dict[str, Any]]] = []
    monkeypatch.setattr(MyCli, 'echo', lambda self, message, **kwargs: echo_calls.append((message, kwargs)))
    myclirc = write_myclirc(
        tmp_path,
        f"""
        [main]
        audit_log = {tmp_path}
        """,
    )

    cli = MyCli(myclirc=myclirc)

    assert cli.logfile is False
    assert echo_calls == [
        (
            'Error: Unable to open the audit log file. Your queries will not be logged.',
            {'err': True, 'fg': 'red'},
        )
    ]


def test_init_reports_unreadable_mylogin_cnf(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    patch_constructor_side_effects(monkeypatch)
    mylogin_path = tmp_path / 'mylogin.cnf'
    mylogin_path.write_text('bad', encoding='utf-8')
    monkeypatch.setattr(client_module, 'get_mylogin_cnf_path', lambda: str(mylogin_path))
    monkeypatch.setattr(client_module, 'open_mylogin_cnf', lambda path: None)
    myclirc = write_myclirc(tmp_path, '')

    MyCli(myclirc=myclirc)

    assert 'Error: Unable to read login path file.' in capsys.readouterr().out


def test_init_appends_readable_mylogin_cnf(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    patch_constructor_side_effects(monkeypatch)
    mylogin_cnf = StringIO('[client]\nuser = alice\n')
    monkeypatch.setattr(client_module, 'get_mylogin_cnf_path', lambda: '/tmp/mylogin.cnf')
    monkeypatch.setattr(client_module, 'open_mylogin_cnf', lambda path: mylogin_cnf)
    myclirc = write_myclirc(tmp_path, '')

    cli = MyCli(myclirc=myclirc)

    assert cli.cnf_files[-1] is mylogin_cnf


def test_close_stops_schema_prefetcher_and_closes_sqlexecute() -> None:
    cli = MyCli.__new__(MyCli)
    stopped: list[bool] = []
    closed: list[bool] = []
    cli.schema_prefetcher = SimpleNamespace(stop=lambda: stopped.append(True))
    cli.sqlexecute = SimpleNamespace(close=lambda: closed.append(True))  # type: ignore[assignment]

    MyCli.close(cli)

    assert stopped == [True]
    assert closed == [True]


def test_run_cli_delegates_to_main_repl(monkeypatch: pytest.MonkeyPatch) -> None:
    cli = MyCli.__new__(MyCli)
    calls: list[MyCli] = []
    monkeypatch.setattr(client_module.repl_package, 'main_repl', lambda target: calls.append(target))

    MyCli.run_cli(cli)

    assert calls == [cli]
