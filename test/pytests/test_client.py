from __future__ import annotations

from io import TextIOWrapper
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import pytest

import mycli.client as client_module
from mycli.client import MyCli


def write_myclirc(tmp_path: Path, content: str) -> str:
    myclirc = tmp_path / 'myclirc'
    myclirc.write_text(content, encoding='utf-8')
    return str(myclirc)


def patch_constructor_side_effects(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(MyCli, 'system_config_files', [])
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
        [connection]
        default_ssl_mode = invalid
        """,
    )

    cli = MyCli(myclirc=myclirc)

    assert cli.ssl_mode is None
    assert echo_calls == [('Invalid config option provided for ssl_mode (invalid); ignoring.', {'err': True, 'fg': 'red'})]


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


def test_init_uses_existing_xdg_config_when_myclirc_is_not_given(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    patch_constructor_side_effects(monkeypatch)
    xdg_config = tmp_path / 'xdg' / 'mycli' / 'myclirc'
    xdg_config.parent.mkdir(parents=True)
    xdg_config.write_text('', encoding='utf-8')
    monkeypatch.setattr(MyCli, 'xdg_config_file', str(xdg_config))

    cli = MyCli(myclirc=None)

    assert cli.config.filename == str(xdg_config)


def test_init_uses_default_myclirc_when_xdg_config_is_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    patch_constructor_side_effects(monkeypatch)
    config_file_args: list[list[str | Any]] = []
    monkeypatch.setattr(MyCli, 'xdg_config_file', '/missing/xdg/myclirc')
    monkeypatch.setattr(client_module.os.path, 'exists', lambda path: False)
    monkeypatch.setattr(client_module, 'write_default_config', lambda destination: None)

    original_read_config_files = client_module.read_config_files

    def read_config_files(files: list[str | Any], *args: Any, **kwargs: Any) -> Any:
        config_file_args.append(files)
        return original_read_config_files(files, *args, **kwargs)

    monkeypatch.setattr(client_module, 'read_config_files', read_config_files)

    MyCli(myclirc=None)

    assert config_file_args[0] == ['~/.myclirc']


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


def test_close_stops_schema_prefetcher_and_closes_sqlexecute() -> None:
    cli = MyCli.__new__(MyCli)
    stopped: list[bool] = []
    closed: list[bool] = []
    tunnel_closed: list[bool] = []
    cli.schema_prefetcher = SimpleNamespace(stop=lambda: stopped.append(True))
    cli.sqlexecute = SimpleNamespace(close=lambda: closed.append(True))  # type: ignore[assignment]
    cast(Any, cli).ssh_tunnel = SimpleNamespace(close=lambda: tunnel_closed.append(True))

    MyCli.close(cli)

    assert stopped == [True]
    assert closed == [True]
    assert tunnel_closed == [True]


def test_close_swallows_cleanup_errors() -> None:
    cli = MyCli.__new__(MyCli)

    def fail() -> None:
        raise RuntimeError('cleanup failed')

    cli.schema_prefetcher = SimpleNamespace(stop=fail)
    cli.sqlexecute = SimpleNamespace(close=fail)  # type: ignore[assignment]
    cast(Any, cli).ssh_tunnel = SimpleNamespace(close=fail)

    MyCli.close(cli)


def test_invalidate_prompt_session_invalidates_prompt_app() -> None:
    cli = MyCli.__new__(MyCli)
    invalidate_calls: list[bool] = []
    cast(Any, cli).prompt_session = SimpleNamespace(app=SimpleNamespace(invalidate=lambda: invalidate_calls.append(True)))

    MyCli._invalidate_prompt_session(cli)

    assert invalidate_calls == [True]


def test_run_cli_delegates_to_main_repl(monkeypatch: pytest.MonkeyPatch) -> None:
    cli = MyCli.__new__(MyCli)
    calls: list[MyCli] = []
    monkeypatch.setattr(client_module.repl_package, 'main_repl', lambda target: calls.append(target))

    MyCli.run_cli(cli)

    assert calls == [cli]
