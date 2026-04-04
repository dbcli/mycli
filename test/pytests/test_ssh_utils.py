from __future__ import annotations

import builtins
import importlib
from pathlib import Path
import sys
from typing import TextIO

import pytest

from mycli.packages import paramiko_stub, ssh_utils


class FakeSSHConfig:
    def __init__(self, parse_error: Exception | None = None) -> None:
        self.parse_error = parse_error
        self.parsed_text: str | None = None

    def parse(self, handle: TextIO) -> None:
        if self.parse_error is not None:
            raise self.parse_error
        self.parsed_text = handle.read()


def test_read_ssh_config_parses_and_returns_config(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    config_path = tmp_path / 'ssh_config'
    config_path.write_text('Host demo\n  HostName example.com\n', encoding='utf-8')
    fake_ssh_config = FakeSSHConfig()

    monkeypatch.setattr(ssh_utils.paramiko.config, 'SSHConfig', lambda: fake_ssh_config)

    result = ssh_utils.read_ssh_config(str(config_path))

    assert result is fake_ssh_config
    assert fake_ssh_config.parsed_text == 'Host demo\n  HostName example.com\n'


def test_read_ssh_config_reports_missing_file_and_exits(monkeypatch: pytest.MonkeyPatch) -> None:
    secho_calls: list[tuple[str, bool, str]] = []

    monkeypatch.setattr(
        ssh_utils.click,
        'secho',
        lambda message, err, fg: secho_calls.append((message, err, fg)),
    )

    with pytest.raises(SystemExit) as excinfo:
        ssh_utils.read_ssh_config('/definitely/missing/ssh_config')

    assert excinfo.value.code == 1
    assert secho_calls == [("[Errno 2] No such file or directory: '/definitely/missing/ssh_config'", True, 'red')]


def test_read_ssh_config_reports_parse_errors_and_exits(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    config_path = tmp_path / 'ssh_config'
    config_path.write_text('Host broken\n', encoding='utf-8')
    fake_ssh_config = FakeSSHConfig(parse_error=RuntimeError('bad config'))
    secho_calls: list[tuple[str, bool, str]] = []

    monkeypatch.setattr(ssh_utils.paramiko.config, 'SSHConfig', lambda: fake_ssh_config)
    monkeypatch.setattr(
        ssh_utils.click,
        'secho',
        lambda message, err, fg: secho_calls.append((message, err, fg)),
    )

    with pytest.raises(SystemExit) as excinfo:
        ssh_utils.read_ssh_config(str(config_path))

    assert excinfo.value.code == 1
    assert secho_calls == [(f'Could not parse SSH configuration file {config_path}:\nbad config ', True, 'red')]


def test_ssh_utils_falls_back_to_paramiko_stub_when_paramiko_is_unavailable(monkeypatch: pytest.MonkeyPatch) -> None:
    original_import = builtins.__import__

    def fake_import(name: str, globals_=None, locals_=None, fromlist=(), level: int = 0):
        if name == 'paramiko':
            raise ImportError('paramiko not installed')
        return original_import(name, globals_, locals_, fromlist, level)

    monkeypatch.delitem(sys.modules, 'paramiko', raising=False)
    monkeypatch.setattr(builtins, '__import__', fake_import)

    reloaded = importlib.reload(ssh_utils)

    assert reloaded.paramiko is paramiko_stub.paramiko

    monkeypatch.undo()
    importlib.reload(ssh_utils)
