from __future__ import annotations

from dataclasses import dataclass
from typing import Any, cast

import mycli.main_modes.list_ssh_config as list_ssh_config_mode


@dataclass
class DummyCliArgs:
    ssh_config_path: str = 'ssh_config'
    verbose: bool = False


class DummySSHConfig:
    def __init__(self, hostnames: list[str] | Exception, lookups: dict[str, dict[str, str]] | None = None) -> None:
        self.hostnames = hostnames
        self.lookups = lookups or {}

    def get_hostnames(self) -> list[str]:
        if isinstance(self.hostnames, Exception):
            raise self.hostnames
        return self.hostnames

    def lookup(self, hostname: str) -> dict[str, str]:
        return self.lookups[hostname]


def main_list_ssh_config(cli_args: DummyCliArgs) -> int:
    return list_ssh_config_mode.main_list_ssh_config(cast(Any, object()), cast(Any, cli_args))


def test_main_list_ssh_config_lists_hostnames(monkeypatch) -> None:
    secho_calls: list[tuple[str, bool | None, str | None]] = []
    ssh_config = DummySSHConfig(['prod', 'staging'])

    monkeypatch.setattr(list_ssh_config_mode, 'read_ssh_config', lambda _path: ssh_config)
    monkeypatch.setattr(
        list_ssh_config_mode.click,
        'secho',
        lambda message, err=None, fg=None: secho_calls.append((message, err, fg)),
    )

    result = main_list_ssh_config(DummyCliArgs(verbose=False))

    assert result == 0
    assert secho_calls == [
        ('prod', None, None),
        ('staging', None, None),
    ]


def test_main_list_ssh_config_lists_verbose_host_details(monkeypatch) -> None:
    secho_calls: list[tuple[str, bool | None, str | None]] = []
    ssh_config = DummySSHConfig(
        ['prod'],
        lookups={'prod': {'hostname': 'db.example.com'}},
    )

    monkeypatch.setattr(list_ssh_config_mode, 'read_ssh_config', lambda _path: ssh_config)
    monkeypatch.setattr(
        list_ssh_config_mode.click,
        'secho',
        lambda message, err=None, fg=None: secho_calls.append((message, err, fg)),
    )

    result = main_list_ssh_config(DummyCliArgs(verbose=True))

    assert result == 0
    assert secho_calls == [('prod : db.example.com', None, None)]


def test_main_list_ssh_config_reports_host_lookup_errors(monkeypatch) -> None:
    secho_calls: list[tuple[str, bool | None, str | None]] = []
    ssh_config = DummySSHConfig(KeyError('bad ssh config'))

    monkeypatch.setattr(list_ssh_config_mode, 'read_ssh_config', lambda _path: ssh_config)
    monkeypatch.setattr(
        list_ssh_config_mode.click,
        'secho',
        lambda message, err=None, fg=None: secho_calls.append((message, err, fg)),
    )

    result = main_list_ssh_config(DummyCliArgs())

    assert result == 1
    assert secho_calls == [('Error reading ssh config', True, 'red')]
