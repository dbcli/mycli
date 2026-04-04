from __future__ import annotations

from dataclasses import dataclass
from types import SimpleNamespace
from typing import Any, cast

import pytest

import mycli.main_modes.execute as execute_mode


@dataclass
class DummyCliArgs:
    execute: str | None
    format: str = 'tsv'
    batch: str | None = None
    checkpoint: str | None = None


@dataclass
class DummyFormatter:
    format_name: str | None = None


class DummyMyCli:
    def __init__(self, run_query_error: Exception | None = None) -> None:
        self.main_formatter = DummyFormatter()
        self.run_query_error = run_query_error
        self.ran_queries: list[tuple[str, str | None]] = []

    def run_query(self, query: str, checkpoint: str | None = None) -> None:
        if self.run_query_error is not None:
            raise self.run_query_error
        self.ran_queries.append((query, checkpoint))


def main_execute_from_cli(mycli: DummyMyCli, cli_args: DummyCliArgs) -> int:
    return execute_mode.main_execute_from_cli(cast(Any, mycli), cast(Any, cli_args))


def fake_sys(stdin_tty: bool) -> SimpleNamespace:
    return SimpleNamespace(stdin=SimpleNamespace(isatty=lambda: stdin_tty))


def test_main_execute_from_cli_returns_error_when_execute_is_missing() -> None:
    assert main_execute_from_cli(DummyMyCli(), DummyCliArgs(execute=None)) == 1


@pytest.mark.parametrize(
    ('format_name', 'original_sql', 'expected_format', 'expected_sql'),
    (
        ('csv', r'select 1\G', 'csv', 'select 1'),
        ('tsv', r'select 2\G', 'tsv', 'select 2'),
        ('table', r'select 3\G', 'ascii', 'select 3'),
        ('vertical', r'select 4\G', 'tsv', r'select 4\G'),
    ),
)
def test_main_execute_from_cli_sets_format_and_runs_query(
    monkeypatch,
    format_name: str,
    original_sql: str,
    expected_format: str,
    expected_sql: str,
) -> None:
    secho_calls: list[tuple[str, bool, str]] = []
    mycli = DummyMyCli()
    cli_args = DummyCliArgs(
        execute=original_sql,
        format=format_name,
        batch='batch.sql',
        checkpoint='cp',
    )

    monkeypatch.setattr(execute_mode, 'sys', fake_sys(stdin_tty=False))
    monkeypatch.setattr(
        execute_mode.click,
        'secho',
        lambda message, err, fg: secho_calls.append((message, err, fg)),
    )

    result = main_execute_from_cli(mycli, cli_args)

    assert result == 0
    assert mycli.main_formatter.format_name == expected_format
    assert mycli.ran_queries == [(expected_sql, 'cp')]
    assert secho_calls == [
        ('Ignoring STDIN since --execute was also given.', True, 'red'),
        ('Ignoring --batch since --execute was also given.', True, 'red'),
    ]


def test_main_execute_from_cli_does_not_warn_when_stdin_is_tty_and_batch_is_unset(monkeypatch) -> None:
    secho_calls: list[tuple[str, bool, str]] = []
    mycli = DummyMyCli()

    monkeypatch.setattr(execute_mode, 'sys', fake_sys(stdin_tty=True))
    monkeypatch.setattr(
        execute_mode.click,
        'secho',
        lambda message, err, fg: secho_calls.append((message, err, fg)),
    )

    result = main_execute_from_cli(mycli, DummyCliArgs(execute='select 1', format='csv'))

    assert result == 0
    assert mycli.main_formatter.format_name == 'csv'
    assert mycli.ran_queries == [('select 1', None)]
    assert secho_calls == []


def test_main_execute_from_cli_reports_query_errors(monkeypatch) -> None:
    secho_calls: list[tuple[str, bool, str]] = []
    mycli = DummyMyCli(run_query_error=RuntimeError('boom'))

    monkeypatch.setattr(execute_mode, 'sys', fake_sys(stdin_tty=True))
    monkeypatch.setattr(
        execute_mode.click,
        'secho',
        lambda message, err, fg: secho_calls.append((message, err, fg)),
    )

    result = main_execute_from_cli(mycli, DummyCliArgs(execute='select 1', format='table'))

    assert result == 1
    assert mycli.main_formatter.format_name == 'ascii'
    assert mycli.ran_queries == []
    assert secho_calls == [('boom', True, 'red')]
