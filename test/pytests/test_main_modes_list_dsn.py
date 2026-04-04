from __future__ import annotations

from dataclasses import dataclass
from typing import Any, cast

import mycli.main_modes.list_dsn as list_dsn_mode


@dataclass
class DummyCliArgs:
    verbose: bool = False


class DummyConfig:
    def __init__(self, value: dict[str, str] | Exception) -> None:
        self.value = value

    def __getitem__(self, key: str) -> dict[str, str]:
        assert key == 'alias_dsn'
        if isinstance(self.value, Exception):
            raise self.value
        return self.value


class DummyMyCli:
    def __init__(self, config: Any) -> None:
        self.config = config


def main_list_dsn(mycli: DummyMyCli, cli_args: DummyCliArgs) -> int:
    return list_dsn_mode.main_list_dsn(cast(Any, mycli), cast(Any, cli_args))


def test_main_list_dsn_lists_aliases_without_values(monkeypatch) -> None:
    secho_calls: list[tuple[str, bool | None, str | None]] = []
    mycli = DummyMyCli(DummyConfig({'prod': 'mysql://u:p@h/db', 'staging': 'mysql://u2:p2@h2/db2'}))

    monkeypatch.setattr(
        list_dsn_mode.click,
        'secho',
        lambda message, err=None, fg=None: secho_calls.append((message, err, fg)),
    )

    result = main_list_dsn(mycli, DummyCliArgs(verbose=False))

    assert result == 0
    assert secho_calls == [
        ('prod', None, None),
        ('staging', None, None),
    ]


def test_main_list_dsn_lists_aliases_with_values_in_verbose_mode(monkeypatch) -> None:
    secho_calls: list[tuple[str, bool | None, str | None]] = []
    mycli = DummyMyCli(DummyConfig({'prod': 'mysql://u:p@h/db'}))

    monkeypatch.setattr(
        list_dsn_mode.click,
        'secho',
        lambda message, err=None, fg=None: secho_calls.append((message, err, fg)),
    )

    result = main_list_dsn(mycli, DummyCliArgs(verbose=True))

    assert result == 0
    assert secho_calls == [('prod : mysql://u:p@h/db', None, None)]


def test_main_list_dsn_reports_invalid_alias_section(monkeypatch) -> None:
    secho_calls: list[tuple[str, bool | None, str | None]] = []
    mycli = DummyMyCli(DummyConfig(KeyError('alias_dsn')))

    monkeypatch.setattr(
        list_dsn_mode.click,
        'secho',
        lambda message, err=None, fg=None: secho_calls.append((message, err, fg)),
    )

    result = main_list_dsn(mycli, DummyCliArgs())

    assert result == 1
    assert secho_calls == [
        (
            'Invalid DSNs found in the config file. Please check the "[alias_dsn]" section in myclirc.',
            True,
            'red',
        )
    ]


def test_main_list_dsn_reports_other_config_errors(monkeypatch) -> None:
    secho_calls: list[tuple[str, bool | None, str | None]] = []
    mycli = DummyMyCli(DummyConfig(RuntimeError('boom')))

    monkeypatch.setattr(
        list_dsn_mode.click,
        'secho',
        lambda message, err=None, fg=None: secho_calls.append((message, err, fg)),
    )

    result = main_list_dsn(mycli, DummyCliArgs())

    assert result == 1
    assert secho_calls == [('boom', True, 'red')]
