from __future__ import annotations

from dataclasses import dataclass
import os
import sys
from tempfile import NamedTemporaryFile
from types import SimpleNamespace
from typing import Any, Literal, cast

from click.testing import CliRunner
import pytest

import mycli.main_modes.batch as batch_mode
import test.pytests.test_main as test_main_module
import test.utils as test_utils

noninteractive_mock_mycli = cast(Any, test_main_module).noninteractive_mock_mycli
TEMPFILE_PREFIX = cast(str, cast(Any, test_utils).TEMPFILE_PREFIX)


@dataclass
class DummyCliArgs:
    format: str = 'tsv'
    noninteractive: bool = True
    throttle: float = 0.0
    checkpoint: str | None = None
    batch: str | None = None


@dataclass
class DummyFormatter:
    format_name: str | None = None


class DummyLogger:
    def __init__(self) -> None:
        self.warning_messages: list[str] = []

    def warning(self, message: str) -> None:
        self.warning_messages.append(message)


class DummyMyCli:
    def __init__(self, destructive_warning: bool = False, run_query_error: Exception | None = None) -> None:
        self.main_formatter = DummyFormatter()
        self.destructive_warning = destructive_warning
        self.destructive_keywords = ('drop',)
        self.logger = DummyLogger()
        self.run_query_error = run_query_error
        self.ran_queries: list[tuple[str, str | None, bool]] = []

    def run_query(self, query: str, checkpoint: str | None = None, new_line: bool = True) -> None:
        if self.run_query_error is not None:
            raise self.run_query_error
        self.ran_queries.append((query, checkpoint, new_line))


class DummyFile:
    def __init__(self, name: str) -> None:
        self.name = name
        self.closed = False

    def close(self) -> None:
        self.closed = True


class DummyProgressBar:
    calls: list[list[int]] = []

    def __init__(self, *args, **kwargs) -> None:
        pass

    def __enter__(self) -> 'DummyProgressBar':
        return self

    def __exit__(self, exc_type, exc, tb) -> Literal[False]:
        return False

    def __call__(self, iterable) -> list[int]:
        values = list(iterable)
        DummyProgressBar.calls.append(values)
        return values


def dispatch_batch_statements(
    mycli: DummyMyCli,
    cli_args: DummyCliArgs,
    statements: str,
    batch_counter: int,
) -> None:
    batch_mode.dispatch_batch_statements(cast(Any, mycli), cast(Any, cli_args), statements, batch_counter)


def main_batch_with_progress_bar(mycli: DummyMyCli, cli_args: DummyCliArgs) -> int:
    return batch_mode.main_batch_with_progress_bar(cast(Any, mycli), cast(Any, cli_args))


def main_batch_without_progress_bar(mycli: DummyMyCli, cli_args: DummyCliArgs) -> int:
    return batch_mode.main_batch_without_progress_bar(cast(Any, mycli), cast(Any, cli_args))


def main_batch_from_stdin(mycli: DummyMyCli, cli_args: DummyCliArgs) -> int:
    return batch_mode.main_batch_from_stdin(cast(Any, mycli), cast(Any, cli_args))


def make_fake_sys(stdin_tty: bool, stderr_tty: bool | None = None) -> SimpleNamespace:
    stderr = SimpleNamespace(isatty=lambda: stderr_tty) if stderr_tty is not None else object()
    return SimpleNamespace(
        stdin=SimpleNamespace(isatty=lambda: stdin_tty),
        stderr=stderr,
        exit=sys.exit,
    )


def patch_progress_mode(monkeypatch, mycli_main, mycli_main_batch) -> None:
    DummyProgressBar.calls.clear()
    monkeypatch.setattr(mycli_main_batch, 'ProgressBar', DummyProgressBar)
    monkeypatch.setattr(mycli_main_batch.prompt_toolkit.output, 'create_output', lambda **kwargs: object())
    fake_sys = make_fake_sys(stdin_tty=False, stderr_tty=True)
    monkeypatch.setattr(mycli_main, 'sys', fake_sys)
    monkeypatch.setattr(mycli_main_batch, 'sys', fake_sys)


def invoke_click_batch(
    runner: CliRunner,
    mycli_main,
    contents: str,
    args: list[str] | None = None,
):
    with NamedTemporaryFile(prefix=TEMPFILE_PREFIX, mode='w', delete=False) as batch_file:
        batch_file.write(contents)
        batch_file.flush()

    try:
        result = runner.invoke(
            mycli_main.click_entrypoint,
            args=['--batch', batch_file.name] + (args or []),
        )
        return result, batch_file.name
    finally:
        if os.path.exists(batch_file.name):
            os.remove(batch_file.name)


@pytest.mark.parametrize(
    ('format_name', 'batch_counter', 'expected'),
    (
        ('csv', 1, 'csv-noheader'),
        ('tsv', 1, 'tsv_noheader'),
        ('table', 1, 'ascii'),
        ('vertical', 1, 'tsv'),
        ('csv', 0, 'csv'),
        ('tsv', 0, 'tsv'),
        ('table', 0, 'ascii'),
        ('vertical', 0, 'tsv'),
    ),
)
def test_dispatch_batch_statements_sets_expected_output_format(
    format_name: str,
    batch_counter: int,
    expected: str,
) -> None:
    mycli = DummyMyCli()
    cli_args = DummyCliArgs(format=format_name, checkpoint='cp')

    dispatch_batch_statements(mycli, cli_args, 'select 1;', batch_counter)

    assert mycli.main_formatter.format_name == expected
    assert mycli.ran_queries == [('select 1;', 'cp', True)]


def test_dispatch_batch_statements_confirms_destructive_queries_before_running(monkeypatch) -> None:
    mycli = DummyMyCli(destructive_warning=True)
    cli_args = DummyCliArgs(noninteractive=False)
    opened_tty = object()

    monkeypatch.setattr(batch_mode, 'is_destructive', lambda _keywords, _statement: True)
    monkeypatch.setattr(batch_mode, 'confirm_destructive_query', lambda _keywords, _statement: True)
    monkeypatch.setattr(batch_mode, 'open', lambda _path: opened_tty, raising=False)
    monkeypatch.setattr(batch_mode, 'sys', SimpleNamespace(stdin=None))

    dispatch_batch_statements(mycli, cli_args, 'drop table demo;', 0)

    assert batch_mode.sys.stdin is opened_tty
    assert mycli.ran_queries == [('drop table demo;', None, True)]


def test_dispatch_batch_statements_skips_query_when_destructive_confirmation_is_rejected(monkeypatch) -> None:
    mycli = DummyMyCli(destructive_warning=True)
    cli_args = DummyCliArgs(noninteractive=False)

    monkeypatch.setattr(batch_mode, 'is_destructive', lambda _keywords, _statement: True)
    monkeypatch.setattr(batch_mode, 'confirm_destructive_query', lambda _keywords, _statement: False)
    monkeypatch.setattr(batch_mode, 'open', lambda _path: object(), raising=False)
    monkeypatch.setattr(batch_mode, 'sys', SimpleNamespace(stdin=None))

    dispatch_batch_statements(mycli, cli_args, 'drop table demo;', 0)

    assert mycli.ran_queries == []


def test_dispatch_batch_statements_raises_when_tty_cannot_be_opened(monkeypatch) -> None:
    mycli = DummyMyCli(destructive_warning=True)
    cli_args = DummyCliArgs(noninteractive=False)

    monkeypatch.setattr(batch_mode, 'is_destructive', lambda _keywords, _statement: True)
    monkeypatch.setattr(batch_mode, 'open', lambda _path: (_ for _ in ()).throw(OSError('tty unavailable')), raising=False)

    with pytest.raises(OSError, match='tty unavailable'):
        dispatch_batch_statements(mycli, cli_args, 'drop table demo;', 0)

    assert mycli.logger.warning_messages == ['Unable to open TTY as stdin.']


def test_dispatch_batch_statements_sleeps_and_reraises_query_errors(monkeypatch) -> None:
    mycli = DummyMyCli(run_query_error=RuntimeError('boom'))
    cli_args = DummyCliArgs(throttle=0.25)
    sleep_calls: list[float] = []
    secho_calls: list[tuple[str, bool, str]] = []

    monkeypatch.setattr(batch_mode.time, 'sleep', lambda seconds: sleep_calls.append(seconds))
    monkeypatch.setattr(
        batch_mode.click,
        'secho',
        lambda message, err, fg: secho_calls.append((message, err, fg)),
    )

    with pytest.raises(RuntimeError, match='boom'):
        dispatch_batch_statements(mycli, cli_args, 'select 1;', 1)

    assert sleep_calls == [0.25]
    assert secho_calls == []


def test_main_batch_with_progress_bar_returns_error_when_batch_is_missing() -> None:
    assert main_batch_with_progress_bar(DummyMyCli(), DummyCliArgs()) == 1


def test_main_batch_with_progress_bar_rejects_non_files(monkeypatch, tmp_path) -> None:
    messages: list[tuple[str, bool, str]] = []
    cli_args = DummyCliArgs(batch=str(tmp_path))

    monkeypatch.setattr(batch_mode.click, 'secho', lambda message, err, fg: messages.append((message, err, fg)))
    monkeypatch.setattr(batch_mode, 'sys', make_fake_sys(stdin_tty=True))

    result = main_batch_with_progress_bar(DummyMyCli(), cli_args)

    assert result == 1
    assert messages == [('--progress is only compatible with a plain file.', True, 'red')]


def test_main_batch_with_progress_bar_handles_open_errors(monkeypatch) -> None:
    messages: list[tuple[str, bool, str]] = []
    cli_args = DummyCliArgs(batch='missing.sql')

    monkeypatch.setattr(batch_mode.os.path, 'exists', lambda _path: False)
    monkeypatch.setattr(batch_mode.click, 'open_file', lambda _path: (_ for _ in ()).throw(FileNotFoundError()))
    monkeypatch.setattr(batch_mode.click, 'secho', lambda message, err, fg: messages.append((message, err, fg)))
    monkeypatch.setattr(batch_mode, 'sys', make_fake_sys(stdin_tty=True))

    result = main_batch_with_progress_bar(DummyMyCli(), cli_args)

    assert result == 1
    assert messages == [('Failed to open --batch file: missing.sql', True, 'red')]


def test_main_batch_with_progress_bar_handles_counting_value_errors(monkeypatch) -> None:
    messages: list[tuple[str, bool, str]] = []
    count_handle = DummyFile('count')
    cli_args = DummyCliArgs(batch='statements.sql')

    monkeypatch.setattr(batch_mode.os.path, 'exists', lambda _path: False)
    monkeypatch.setattr(batch_mode.click, 'open_file', lambda _path: count_handle)
    monkeypatch.setattr(batch_mode, 'statements_from_filehandle', lambda _handle: (_ for _ in ()).throw(ValueError('bad sql')))
    monkeypatch.setattr(batch_mode.click, 'secho', lambda message, err, fg: messages.append((message, err, fg)))
    monkeypatch.setattr(batch_mode, 'sys', make_fake_sys(stdin_tty=True))

    result = main_batch_with_progress_bar(DummyMyCli(), cli_args)

    assert result == 1
    assert messages == [('Error reading --batch file: statements.sql: bad sql', True, 'red')]


def test_main_batch_with_progress_bar_processes_all_statements(monkeypatch) -> None:
    messages: list[tuple[str, bool, str]] = []
    count_handle = DummyFile('count')
    run_handle = DummyFile('run')
    open_calls: list[str] = []
    dispatch_calls: list[tuple[str, int]] = []
    cli_args = DummyCliArgs(batch='statements.sql')

    def fake_open_file(path: str) -> DummyFile:
        open_calls.append(path)
        return count_handle if len(open_calls) == 1 else run_handle

    def fake_statements_from_filehandle(handle: DummyFile):
        if handle is count_handle:
            return iter([('select 1;', 0), ('select 2;', 1)])
        return iter([('select 1;', 0), ('select 2;', 1)])

    DummyProgressBar.calls.clear()
    monkeypatch.setattr(batch_mode.os.path, 'exists', lambda _path: False)
    monkeypatch.setattr(batch_mode.click, 'open_file', fake_open_file)
    monkeypatch.setattr(batch_mode, 'statements_from_filehandle', fake_statements_from_filehandle)
    monkeypatch.setattr(
        batch_mode,
        'dispatch_batch_statements',
        lambda _mycli, _cli_args, statement, counter: dispatch_calls.append((statement, counter)),
    )
    monkeypatch.setattr(batch_mode, 'ProgressBar', DummyProgressBar)
    monkeypatch.setattr(batch_mode.prompt_toolkit.output, 'create_output', lambda **_kwargs: object())
    monkeypatch.setattr(batch_mode.click, 'secho', lambda message, err, fg: messages.append((message, err, fg)))
    monkeypatch.setattr(batch_mode, 'sys', make_fake_sys(stdin_tty=False))

    result = main_batch_with_progress_bar(DummyMyCli(), cli_args)

    assert result == 0
    assert messages == [('Ignoring STDIN since --batch was also given.', True, 'yellow')]
    assert dispatch_calls == [('select 1;', 0), ('select 2;', 1)]
    assert DummyProgressBar.calls == [[0, 1]]
    assert count_handle.closed is True
    assert run_handle.closed is True


def test_main_batch_with_progress_bar_returns_error_when_dispatch_fails(monkeypatch) -> None:
    messages: list[tuple[str, bool, str]] = []
    count_handle = DummyFile('count')
    run_handle = DummyFile('run')
    open_calls = 0
    cli_args = DummyCliArgs(batch='statements.sql')

    def fake_open_file(_path: str) -> DummyFile:
        nonlocal open_calls
        open_calls += 1
        return count_handle if open_calls == 1 else run_handle

    def fake_statements_from_filehandle(handle: DummyFile):
        if handle is count_handle:
            return iter([('select 1;', 0)])
        return iter([('select 1;', 0)])

    monkeypatch.setattr(batch_mode.os.path, 'exists', lambda _path: False)
    monkeypatch.setattr(batch_mode.click, 'open_file', fake_open_file)
    monkeypatch.setattr(batch_mode, 'statements_from_filehandle', fake_statements_from_filehandle)
    monkeypatch.setattr(batch_mode, 'ProgressBar', DummyProgressBar)
    monkeypatch.setattr(batch_mode.prompt_toolkit.output, 'create_output', lambda **_kwargs: object())
    monkeypatch.setattr(
        batch_mode,
        'dispatch_batch_statements',
        lambda _mycli, _cli_args, _statement, _counter: (_ for _ in ()).throw(OSError('dispatch failed')),
    )
    monkeypatch.setattr(batch_mode.click, 'secho', lambda message, err, fg: messages.append((message, err, fg)))
    monkeypatch.setattr(batch_mode, 'sys', make_fake_sys(stdin_tty=True))

    result = main_batch_with_progress_bar(DummyMyCli(), cli_args)

    assert result == 1
    assert messages == [('dispatch failed', True, 'red')]
    assert run_handle.closed is True


def test_main_batch_without_progress_bar_returns_error_when_batch_is_missing() -> None:
    assert main_batch_without_progress_bar(DummyMyCli(), DummyCliArgs()) == 1


def test_main_batch_without_progress_bar_handles_open_errors(monkeypatch) -> None:
    messages: list[tuple[str, bool, str]] = []
    cli_args = DummyCliArgs(batch='missing.sql')

    monkeypatch.setattr(batch_mode.click, 'open_file', lambda _path: (_ for _ in ()).throw(FileNotFoundError()))
    monkeypatch.setattr(batch_mode.click, 'secho', lambda message, err, fg: messages.append((message, err, fg)))
    monkeypatch.setattr(batch_mode, 'sys', make_fake_sys(stdin_tty=True))

    result = main_batch_without_progress_bar(DummyMyCli(), cli_args)

    assert result == 1
    assert messages == [('Failed to open --batch file: missing.sql', True, 'red')]


def test_main_batch_without_progress_bar_processes_statements(monkeypatch) -> None:
    messages: list[tuple[str, bool, str]] = []
    batch_handle = DummyFile('run')
    dispatch_calls: list[tuple[str, int]] = []
    cli_args = DummyCliArgs(batch='statements.sql')

    monkeypatch.setattr(batch_mode.click, 'open_file', lambda _path: batch_handle)
    monkeypatch.setattr(batch_mode, 'statements_from_filehandle', lambda _handle: iter([('select 1;', 0), ('select 2;', 1)]))
    monkeypatch.setattr(
        batch_mode,
        'dispatch_batch_statements',
        lambda _mycli, _cli_args, statement, counter: dispatch_calls.append((statement, counter)),
    )
    monkeypatch.setattr(batch_mode.click, 'secho', lambda message, err, fg: messages.append((message, err, fg)))
    monkeypatch.setattr(batch_mode, 'sys', make_fake_sys(stdin_tty=False))

    result = main_batch_without_progress_bar(DummyMyCli(), cli_args)

    assert result == 0
    assert messages == [('Ignoring STDIN since --batch was also given.', True, 'red')]
    assert dispatch_calls == [('select 1;', 0), ('select 2;', 1)]
    assert batch_handle.closed is True


def test_main_batch_without_progress_bar_returns_error_when_iteration_fails(monkeypatch) -> None:
    messages: list[tuple[str, bool, str]] = []
    batch_handle = DummyFile('run')
    cli_args = DummyCliArgs(batch='statements.sql')

    monkeypatch.setattr(batch_mode.click, 'open_file', lambda _path: batch_handle)
    monkeypatch.setattr(batch_mode, 'statements_from_filehandle', lambda _handle: (_ for _ in ()).throw(ValueError('bad sql')))
    monkeypatch.setattr(batch_mode.click, 'secho', lambda message, err, fg: messages.append((message, err, fg)))
    monkeypatch.setattr(batch_mode, 'sys', make_fake_sys(stdin_tty=True))

    result = main_batch_without_progress_bar(DummyMyCli(), cli_args)

    assert result == 1
    assert messages == [('bad sql', True, 'red')]


def test_main_batch_from_stdin_processes_statements(monkeypatch) -> None:
    dispatch_calls: list[tuple[str, int]] = []
    batch_handle = object()

    monkeypatch.setattr(batch_mode.click, 'get_text_stream', lambda _name: batch_handle)
    monkeypatch.setattr(batch_mode, 'statements_from_filehandle', lambda _handle: iter([('select 1;', 0), ('select 2;', 1)]))
    monkeypatch.setattr(
        batch_mode,
        'dispatch_batch_statements',
        lambda _mycli, _cli_args, statement, counter: dispatch_calls.append((statement, counter)),
    )

    result = main_batch_from_stdin(DummyMyCli(), DummyCliArgs())

    assert result == 0
    assert dispatch_calls == [('select 1;', 0), ('select 2;', 1)]


def test_main_batch_from_stdin_returns_error_for_value_errors(monkeypatch) -> None:
    messages: list[tuple[str, bool, str]] = []

    monkeypatch.setattr(batch_mode.click, 'get_text_stream', lambda _name: object())
    monkeypatch.setattr(batch_mode, 'statements_from_filehandle', lambda _handle: (_ for _ in ()).throw(ValueError('bad stdin')))
    monkeypatch.setattr(batch_mode.click, 'secho', lambda message, err, fg: messages.append((message, err, fg)))

    result = main_batch_from_stdin(DummyMyCli(), DummyCliArgs())

    assert result == 1
    assert messages == [('bad stdin', True, 'red')]


@pytest.mark.parametrize(
    ('contents', 'extra_args', 'expected_queries', 'expected_progress'),
    (
        ('select 2;', [], ['select 2;'], None),
        ('select 2; select 3;\nselect 4;\n', [], ['select 2;', 'select 3;', 'select 4;'], None),
        ('select 2;\nselect 2;\nselect 2;\n', ['--progress'], ['select 2;', 'select 2;', 'select 2;'], [[0, 1, 2]]),
        ('select 2; select 3;\nselect 4;\n', ['--progress'], ['select 2;', 'select 3;', 'select 4;'], [[0, 1, 2]]),
    ),
)
def test_click_batch_file_modes(monkeypatch, contents: str, extra_args: list[str], expected_queries: list[str], expected_progress) -> None:
    mycli_main, mycli_main_batch, MockMyCli = noninteractive_mock_mycli(monkeypatch)
    runner = CliRunner()
    MockMyCli.ran_queries = []

    if '--progress' in extra_args:
        patch_progress_mode(monkeypatch, mycli_main, mycli_main_batch)

    result, _batch_file_name = invoke_click_batch(runner, mycli_main, contents, extra_args)

    assert result.exit_code == 0
    assert MockMyCli.ran_queries == expected_queries
    if expected_progress is not None:
        assert DummyProgressBar.calls == expected_progress


def test_batch_file_with_progress_requires_plain_file(monkeypatch, tmp_path) -> None:
    mycli_main, mycli_main_batch, MockMyCli = noninteractive_mock_mycli(monkeypatch)
    runner = CliRunner()

    patch_progress_mode(monkeypatch, mycli_main, mycli_main_batch)

    result = runner.invoke(
        mycli_main.click_entrypoint,
        args=['--batch', str(tmp_path), '--progress'],
    )

    assert result.exit_code != 0
    assert '--progress is only compatible with a plain file.' in result.output
    assert MockMyCli.ran_queries == []


def test_batch_file_open_error(monkeypatch) -> None:
    mycli_main, _mycli_main_batch, MockMyCli = noninteractive_mock_mycli(monkeypatch)
    runner = CliRunner()

    result = runner.invoke(mycli_main.click_entrypoint, args=['--batch', 'definitely_missing_file.sql'])

    assert result.exit_code != 0
    assert 'Failed to open --batch file' in result.output
    assert MockMyCli.ran_queries == []
