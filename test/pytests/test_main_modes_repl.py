from __future__ import annotations

import builtins
from collections.abc import Generator, Iterator
from dataclasses import dataclass
from io import StringIO
import os
from types import SimpleNamespace
from typing import Any, Literal, cast

from prompt_toolkit.formatted_text import to_plain_text
import pymysql
import pytest

import mycli.main as main_module
import mycli.main_modes.repl as repl_mode
from mycli.packages.sqlresult import SQLResult


class DummyLogger:
    def __init__(self) -> None:
        self.debug_calls: list[tuple[tuple[Any, ...], dict[str, Any]]] = []
        self.error_calls: list[tuple[tuple[Any, ...], dict[str, Any]]] = []

    def debug(self, *args: Any, **kwargs: Any) -> None:
        self.debug_calls.append((args, kwargs))

    def error(self, *args: Any, **kwargs: Any) -> None:
        self.error_calls.append((args, kwargs))


@dataclass
class DummyFormatterWithQuery:
    query: str = ''


class FakeApp:
    def __init__(self, text: str = '', render_counter: int = 0) -> None:
        self.current_buffer = SimpleNamespace(text=text)
        self.render_counter = render_counter
        self.ttimeoutlen: float | None = None


class FakePromptOutput:
    def __init__(self, columns: int = 80, rows: int = 24) -> None:
        self.columns = columns
        self.rows = rows
        self.bell_count = 0

    def get_size(self) -> SimpleNamespace:
        return SimpleNamespace(columns=self.columns, rows=self.rows)

    def bell(self) -> None:
        self.bell_count += 1


class FakePromptSession:
    def __init__(self, responses: list[Any] | None = None, columns: int = 80, rows: int = 24) -> None:
        self.responses = list(responses or [])
        self.output = FakePromptOutput(columns=columns, rows=rows)
        self.app = FakeApp()
        self.prompt_calls: list[dict[str, Any]] = []

    def prompt(self, **kwargs: Any) -> str:
        self.prompt_calls.append(dict(kwargs))
        if not self.responses:
            raise EOFError()
        response = self.responses.pop(0)
        if isinstance(response, BaseException):
            raise response
        return response


class FakeCursorBase:
    def __init__(
        self,
        rows: list[tuple[Any, ...]] | None = None,
        rowcount: int = 0,
        warning_count: int = 0,
    ) -> None:
        self._rows = list(rows or [])
        self.rowcount = rowcount
        self.warning_count = warning_count

    def __iter__(self) -> Iterator[tuple[Any, ...]]:
        return iter(self._rows)


class FakeConnection:
    def __init__(self, ping_exc: Exception | None = None, cursor_value: Any = 'cursor') -> None:
        self.ping_exc = ping_exc
        self.cursor_value = cursor_value
        self.ping_calls: list[bool] = []

    def ping(self, reconnect: bool = False) -> None:
        self.ping_calls.append(reconnect)
        if self.ping_exc is not None:
            raise self.ping_exc

    def cursor(self) -> Any:
        return self.cursor_value


class ReusableLock:
    def __enter__(self) -> 'ReusableLock':
        return self

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> Literal[False]:
        return False


def sqlresult_generator(*results: SQLResult) -> Generator[SQLResult, None, None]:
    for result in results:
        yield result


class FakeResourceTree:
    def __init__(self, files: dict[str, str], path: str | None = None) -> None:
        self.files = files
        self.path = path

    def joinpath(self, path: str) -> 'FakeResourceTree':
        return FakeResourceTree(self.files, path)

    def open(self, mode: str) -> StringIO:
        assert self.path is not None
        if self.path not in self.files:
            raise FileNotFoundError(self.path)
        return StringIO(self.files[self.path])


def make_repl_cli(sqlexecute: Any | None = None) -> Any:
    cli = SimpleNamespace()
    cli.logger = DummyLogger()
    cli.query_history = []
    cli.last_prompt_message = repl_mode.ANSI('')
    cli.last_custom_toolbar_message = repl_mode.ANSI('')
    cli.prompt_lines = 0
    cli.default_prompt = r'\t \u@\h:\d> '
    cli.default_prompt_splitln = r'\u@\h\n(\t):\d>'
    cli.max_len_prompt = 45
    cli.prompt_format = cli.default_prompt
    cli.multiline_continuation_char = '>'
    cli.toolbar_format = 'default'
    cli.less_chatty = True
    cli.keepalive_ticks = None
    cli._keepalive_counter = 0
    cli.auto_vertical_output = False
    cli.beep_after_seconds = 0.0
    cli.show_warnings = False
    cli.null_string = '<null>'
    cli.numeric_alignment = 'right'
    cli.binary_display = None
    cli.prompt_app = None
    cli.post_redirect_command = None
    cli.logfile = None
    cli.smart_completion = False
    cli.config = {'history_file': '~/.mycli-history-testing'}
    cli.key_bindings = 'emacs'
    cli.wider_completion_menu = False
    cli._completer_lock = ReusableLock()
    cli.completer = object()
    cli.syntax_style = 'native'
    cli.cli_style = {}
    cli.emacs_ttimeoutlen = 1.0
    cli.vi_ttimeoutlen = 2.0
    cli.destructive_warning = False
    cli.destructive_keywords = ['drop']
    cli.llm_prompt_field_truncate = 0
    cli.llm_prompt_section_truncate = 0
    cli.main_formatter = DummyFormatterWithQuery()
    cli.redirect_formatter = DummyFormatterWithQuery()
    cli.pager_configured = 0
    refresh_calls: list[bool] = []
    output_calls: list[tuple[list[str], Any, bool]] = []
    echo_calls: list[str] = []
    timing_calls: list[tuple[str, bool]] = []
    log_queries: list[str] = []
    cli.refresh_calls = refresh_calls
    cli.output_calls = output_calls
    cli.echo_calls = echo_calls
    cli.timing_calls = timing_calls
    cli.log_queries = log_queries
    cli.title_calls = 0
    cli.sqlexecute = sqlexecute
    cli.get_reserved_space = lambda: 3
    cli.get_last_query = lambda: cli.query_history[-1].query if cli.query_history else None
    cli.configure_pager = lambda: setattr(cli, 'pager_configured', cli.pager_configured + 1)

    def refresh_completions(reset: bool = False) -> list[SQLResult]:
        cli.refresh_calls.append(reset)
        return [SQLResult(status='refresh')]

    cli.refresh_completions = refresh_completions
    cli.set_all_external_titles = lambda: setattr(cli, 'title_calls', cli.title_calls + 1)

    def output_timing(timing: str, is_warnings_style: bool = False) -> None:
        cli.timing_calls.append((timing, is_warnings_style))

    cli.output_timing = output_timing

    def log_query(text: str) -> None:
        cli.log_queries.append(text)

    cli.log_query = log_query
    cli.reconnect = lambda database='': False

    def echo(message: Any, **kwargs: Any) -> None:
        cli.echo_calls.append(str(message))

    cli.echo = echo

    def format_sqlresult(result: SQLResult, **kwargs: Any) -> Iterator[str]:
        return iter([str(kwargs.get('max_width')), result.status_plain or 'row'])

    cli.format_sqlresult = format_sqlresult

    def output(formatted: Any, result: Any, is_warnings_style: bool = False) -> None:
        cli.output_calls.append((list(formatted), result, is_warnings_style))

    cli.output = output
    cli.get_prompt = lambda string, render_counter: f'{string}:{render_counter}'
    return cli


def patch_repl_runtime_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(repl_mode.special, 'set_expanded_output', lambda value: None)
    monkeypatch.setattr(repl_mode.special, 'set_forced_horizontal_output', lambda value: None)
    monkeypatch.setattr(repl_mode.special, 'is_llm_command', lambda text: False)
    monkeypatch.setattr(repl_mode.special, 'is_expanded_output', lambda: False)
    monkeypatch.setattr(repl_mode.special, 'is_redirected', lambda: False)
    monkeypatch.setattr(repl_mode.special, 'is_timing_enabled', lambda: False)
    monkeypatch.setattr(repl_mode.special, 'write_tee', lambda *args, **kwargs: None)
    monkeypatch.setattr(repl_mode.special, 'unset_once_if_written', lambda *args, **kwargs: None)
    monkeypatch.setattr(repl_mode.special, 'flush_pipe_once_if_written', lambda *args, **kwargs: None)
    monkeypatch.setattr(repl_mode.special, 'close_tee', lambda: None)
    monkeypatch.setattr(repl_mode, 'handle_editor_command', lambda mycli, text, inputhook, loaded_message_fn: text)
    monkeypatch.setattr(repl_mode, 'handle_clip_command', lambda mycli, text: False)
    monkeypatch.setattr(repl_mode, 'is_redirect_command', lambda text: False)
    monkeypatch.setattr(repl_mode, 'confirm_destructive_query', lambda keywords, text: None)
    monkeypatch.setattr(repl_mode, 'need_completion_refresh', lambda text: False)
    monkeypatch.setattr(repl_mode, 'need_completion_reset', lambda text: False)
    monkeypatch.setattr(repl_mode, 'is_dropping_database', lambda text, dbname: False)
    monkeypatch.setattr(repl_mode, 'is_mutating', lambda status: False)


def test_complete_while_typing_filter_covers_threshold_and_word_rules(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(repl_mode, 'MIN_COMPLETION_TRIGGER', 3)
    monkeypatch.setattr(repl_mode, 'get_app', lambda: SimpleNamespace(current_buffer=SimpleNamespace(text='ab')))
    assert repl_mode.complete_while_typing_filter() is False

    monkeypatch.setattr(repl_mode, 'get_app', lambda: SimpleNamespace(current_buffer=SimpleNamespace(text='abc')))
    assert repl_mode.complete_while_typing_filter() is True

    monkeypatch.setattr(repl_mode, 'get_app', lambda: SimpleNamespace(current_buffer=SimpleNamespace(text='source xyz')))
    assert repl_mode.complete_while_typing_filter() is True

    monkeypatch.setattr(repl_mode, 'get_app', lambda: SimpleNamespace(current_buffer=SimpleNamespace(text='source x/')))
    assert repl_mode.complete_while_typing_filter() is False

    monkeypatch.setattr(repl_mode, 'get_app', lambda: SimpleNamespace(current_buffer=SimpleNamespace(text='\\. abc')))
    assert repl_mode.complete_while_typing_filter() is True

    monkeypatch.setattr(repl_mode, 'get_app', lambda: SimpleNamespace(current_buffer=SimpleNamespace(text='\\. a/')))
    assert repl_mode.complete_while_typing_filter() is False

    monkeypatch.setattr(repl_mode, 'get_app', lambda: SimpleNamespace(current_buffer=SimpleNamespace(text='select abc')))
    assert repl_mode.complete_while_typing_filter() is True

    monkeypatch.setattr(repl_mode, 'get_app', lambda: SimpleNamespace(current_buffer=SimpleNamespace(text='select a!')))
    assert repl_mode.complete_while_typing_filter() is False

    monkeypatch.setattr(repl_mode, 'MIN_COMPLETION_TRIGGER', 1)
    assert repl_mode.complete_while_typing_filter() is True


def test_repl_main_module_and_create_history(monkeypatch: pytest.MonkeyPatch) -> None:
    cli = make_repl_cli()
    monkeypatch.setenv('MYCLI_HISTFILE', '~/override-history')
    monkeypatch.setattr(repl_mode, 'dir_path_exists', lambda path: True)
    monkeypatch.setattr(repl_mode, 'FileHistoryWithTimestamp', lambda path: f'history:{path}')
    assert repl_mode._main_module() is main_module
    history = cast(Any, repl_mode._create_history(cli))
    assert history == f'history:{os.path.expanduser("~/override-history")}'

    monkeypatch.delenv('MYCLI_HISTFILE')
    monkeypatch.setattr(repl_mode, 'dir_path_exists', lambda path: False)
    assert repl_mode._create_history(cli) is None
    assert 'Unable to open the history file' in cli.echo_calls[-1]


def test_repl_picker_helpers_cover_present_and_missing_resources(monkeypatch: pytest.MonkeyPatch) -> None:
    files = {
        'AUTHORS': '* Alice\n* Bob\n',
        'SPONSORS': '* Carol\n',
        'TIPS': '# comment\nTip 1\n\nTip 2\n',
    }
    monkeypatch.setattr(repl_mode.resources, 'files', lambda package: FakeResourceTree(files))
    monkeypatch.setattr(repl_mode.random, 'choice', lambda seq: seq[0])
    assert repl_mode._thanks_picker() == 'Alice'
    assert repl_mode._tips_picker() == 'Tip 1'

    monkeypatch.setattr(repl_mode.resources, 'files', lambda package: FakeResourceTree({}))
    assert repl_mode._thanks_picker() == 'our sponsors'
    assert repl_mode._tips_picker() == r'\? or "help" for help!'


def test_repl_show_startup_banner_and_prompt_helpers(monkeypatch: pytest.MonkeyPatch) -> None:
    cli = make_repl_cli(SimpleNamespace(server_info='Server'))
    printed: list[str] = []
    monkeypatch.setattr(builtins, 'print', lambda *args, **kwargs: printed.append(' '.join(str(x) for x in args)))
    monkeypatch.setattr(repl_mode.random, 'random', lambda: 0.4)
    monkeypatch.setattr(repl_mode, '_thanks_picker', lambda: 'Alice')
    monkeypatch.setattr(repl_mode, '_tips_picker', lambda: 'Tip')

    cli.less_chatty = False
    repl_mode._show_startup_banner(cli, cli.sqlexecute)
    monkeypatch.setattr(repl_mode.random, 'random', lambda: 0.6)
    repl_mode._show_startup_banner(cli, cli.sqlexecute)
    cli.less_chatty = True
    repl_mode._show_startup_banner(cli, cli.sqlexecute)
    assert any('Thanks to the contributor' in line for line in printed)
    assert any('Tip — Tip' in line for line in printed)

    cli.get_prompt = lambda string, render_counter: '0123456' if string == cli.default_prompt else 'a\nb'
    cli.max_len_prompt = 5
    prompt_text = to_plain_text(repl_mode._get_prompt_message(cli, cast(Any, FakeApp(text='', render_counter=2))))
    assert prompt_text == 'a\nb'
    assert cli.prompt_lines == 2

    cli.last_prompt_message = repl_mode.ANSI('cached')
    assert to_plain_text(repl_mode._get_prompt_message(cli, cast(Any, FakeApp(text='typing', render_counter=3)))) == 'cached'

    cli.prompt_format = 'custom'
    cli.prompt_lines = 0
    cli.get_prompt = lambda string, render_counter: 'single'
    assert to_plain_text(repl_mode._get_prompt_message(cli, cast(Any, FakeApp(text='', render_counter=4)))) == 'single'
    assert cli.prompt_lines == 1

    assert repl_mode._get_continuation(cli, 4, 0, 0) == [('class:continuation', '  > ')]
    cli.multiline_continuation_char = ''
    assert repl_mode._get_continuation(cli, 4, 0, 0) == [('class:continuation', '')]
    cli.multiline_continuation_char = None
    assert repl_mode._get_continuation(cli, 4, 0, 0) == [('class:continuation', ' ')]


def test_output_results_covers_watch_warning_timing_beep_and_interrupts(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeSQLExecute:
        def run(self, text: str) -> list[SQLResult]:
            assert text == 'SHOW WARNINGS'
            return [SQLResult(status='warning', rows=[('warn',)])]

    cli = make_repl_cli(FakeSQLExecute())
    cli.auto_vertical_output = True
    cli.prompt_app = FakePromptSession(columns=91)
    cli.beep_after_seconds = 0.1
    cli.show_warnings = True
    state = repl_mode.ReplState()
    format_widths: list[int | None] = []

    def format_sqlresult(result: SQLResult, **kwargs: Any) -> Iterator[str]:
        format_widths.append(kwargs.get('max_width'))
        return iter([result.status_plain or 'row'])

    cli.format_sqlresult = format_sqlresult
    time_values = iter([0.2, 1.0, 2.0, 3.0, 3.2])
    monkeypatch.setattr(repl_mode.time, 'time', lambda: next(time_values))
    monkeypatch.setattr(repl_mode.special, 'is_expanded_output', lambda: False)
    monkeypatch.setattr(repl_mode.special, 'is_redirected', lambda: False)
    monkeypatch.setattr(repl_mode.special, 'is_timing_enabled', lambda: True)
    monkeypatch.setattr(repl_mode, 'Cursor', FakeCursorBase)
    monkeypatch.setattr(repl_mode, 'is_select', lambda status: False)
    monkeypatch.setattr(repl_mode, 'is_mutating', lambda status: status == 'mut')

    results = sqlresult_generator(
        SQLResult(status='watch', command={'name': 'watch', 'seconds': '1'}),
        SQLResult(status='mut', rows=cast(Any, FakeCursorBase(rowcount=1, warning_count=1))),
    )

    repl_mode._output_results(cli, state, results, start=0.0)

    assert state.mutating is True
    assert format_widths[:2] == [91, 91]
    assert cli.prompt_app.output.bell_count == 2
    assert '' in cli.echo_calls
    assert any(is_warnings_style is True for _, _, is_warnings_style in cli.output_calls)
    assert any(is_warnings_style is False for _, is_warnings_style in cli.timing_calls)
    assert any(is_warnings_style is True for _, is_warnings_style in cli.timing_calls)

    cli_interrupt = make_repl_cli(SimpleNamespace())
    cli_interrupt.echo = lambda message, **kwargs: (
        (_ for _ in ()).throw(KeyboardInterrupt()) if message == '' else cli_interrupt.echo_calls.append(str(message))
    )
    cli_interrupt.output = lambda formatted, result, is_warnings_style=False: (_ for _ in ()).throw(KeyboardInterrupt())
    monkeypatch.setattr(repl_mode.special, 'is_timing_enabled', lambda: False)
    monkeypatch.setattr(repl_mode, 'is_select', lambda status: False)
    monkeypatch.setattr(repl_mode.time, 'time', lambda: 0.0)
    repl_mode._output_results(
        cli_interrupt,
        repl_mode.ReplState(),
        sqlresult_generator(SQLResult(status='first'), SQLResult(status='second')),
        start=0.0,
    )


def test_output_results_handles_abort_default_width_and_bad_watch(monkeypatch: pytest.MonkeyPatch) -> None:
    cli = make_repl_cli(SimpleNamespace())
    cli.auto_vertical_output = True
    widths: list[int | None] = []

    def format_sqlresult_with_width(result: SQLResult, **kwargs: Any) -> Iterator[str]:
        widths.append(kwargs.get('max_width'))
        return iter([result.status_plain or 'row'])

    cli.format_sqlresult = format_sqlresult_with_width
    monkeypatch.setattr(repl_mode, 'Cursor', FakeCursorBase)
    monkeypatch.setattr(repl_mode, 'is_select', lambda status: status == 'select')
    monkeypatch.setattr(repl_mode, 'confirm', lambda text: False)
    repl_mode._output_results(
        cli,
        repl_mode.ReplState(),
        sqlresult_generator(SQLResult(status='select', rows=cast(Any, FakeCursorBase(rowcount=1001)))),
        start=0.0,
    )
    assert 'The result set has more than 1000 rows.' in cli.echo_calls
    assert 'Aborted!' in cli.echo_calls

    repl_mode._output_results(
        cli,
        repl_mode.ReplState(),
        sqlresult_generator(SQLResult(status='ok')),
        start=0.0,
    )
    assert widths[-1] == repl_mode.DEFAULT_WIDTH

    monkeypatch.setattr(repl_mode, 'is_select', lambda status: False)
    with pytest.raises(SystemExit):
        repl_mode._output_results(
            cli,
            repl_mode.ReplState(),
            sqlresult_generator(
                SQLResult(status='watch', command={'name': 'watch', 'seconds': '1'}),
                SQLResult(status='watch', command={'name': 'watch', 'seconds': 'bad'}),
            ),
            start=0.0,
        )


def test_keepalive_hook_covers_threshold_and_errors() -> None:
    cli = make_repl_cli(SimpleNamespace(conn=FakeConnection()))
    repl_mode._keepalive_hook(cli, None)
    assert cli._keepalive_counter == 0

    cli.keepalive_ticks = 0
    repl_mode._keepalive_hook(cli, None)
    assert cli._keepalive_counter == 0

    cli.keepalive_ticks = 1
    repl_mode._keepalive_hook(cli, None)
    assert cli._keepalive_counter == 1
    repl_mode._keepalive_hook(cli, None)
    assert cli._keepalive_counter == 0
    assert cli.sqlexecute.conn.ping_calls == [False]

    cli.sqlexecute.conn = FakeConnection(ping_exc=RuntimeError('boom'))
    repl_mode._keepalive_hook(cli, None)
    repl_mode._keepalive_hook(cli, None)
    assert any('keepalive ping error' in call[0][0] for call in cli.logger.debug_calls)


def test_build_prompt_session_covers_toolbar_modes_and_editing_modes(monkeypatch: pytest.MonkeyPatch) -> None:
    captured_kwargs: list[dict[str, Any]] = []
    toolbar_help: list[bool] = []

    def fake_prompt_session(**kwargs: Any) -> FakePromptSession:
        captured_kwargs.append(kwargs)
        return FakePromptSession()

    monkeypatch.setattr(repl_mode, 'PromptSession', fake_prompt_session)
    monkeypatch.setattr(repl_mode, 'style_factory_ptoolkit', lambda *args, **kwargs: 'style')
    monkeypatch.setattr(repl_mode, 'cli_is_multiline', lambda mycli: False)

    def fake_toolbar_tokens(mycli: Any, show_help: Any, fmt: str) -> str:
        toolbar_help.append(show_help())
        return 'toolbar'

    monkeypatch.setattr(repl_mode, 'create_toolbar_tokens_func', fake_toolbar_tokens)

    cli = make_repl_cli(SimpleNamespace())
    state = repl_mode.ReplState()
    cli.toolbar_format = 'none'
    cli.key_bindings = 'vi'
    cli.wider_completion_menu = True
    repl_mode._build_prompt_session(cli, state, history=cast(Any, 'history'), key_bindings=cast(Any, 'bindings'))
    first_kwargs = captured_kwargs[-1]
    assert first_kwargs['bottom_toolbar'] is None
    assert first_kwargs['complete_style'] == repl_mode.CompleteStyle.MULTI_COLUMN
    assert first_kwargs['editing_mode'] == repl_mode.EditingMode.VI
    assert cli.prompt_app.app.ttimeoutlen == cli.vi_ttimeoutlen

    cli.toolbar_format = 'default'
    cli.key_bindings = 'emacs'
    cli.wider_completion_menu = False
    state.iterations = 0
    repl_mode._build_prompt_session(cli, state, history=cast(Any, 'history'), key_bindings=cast(Any, 'bindings'))
    latest_kwargs = captured_kwargs[-1]
    assert latest_kwargs['bottom_toolbar'] == 'toolbar'
    assert latest_kwargs['complete_style'] == repl_mode.CompleteStyle.COLUMN
    assert latest_kwargs['editing_mode'] == repl_mode.EditingMode.EMACS
    assert toolbar_help == [True]
    assert cli.prompt_app.app.ttimeoutlen == cli.emacs_ttimeoutlen
    assert latest_kwargs['prompt_continuation'](4, 0, 0) == [('class:continuation', '  > ')]


def test_one_iteration_handles_prompt_interrupt_empty_editor_clip_and_clip_true(monkeypatch: pytest.MonkeyPatch) -> None:
    patch_repl_runtime_defaults(monkeypatch)
    cli = make_repl_cli(SimpleNamespace(run=lambda text: iter([SQLResult(status='ok')]), conn=FakeConnection()))
    cli.keepalive_ticks = 1
    cli.prompt_app = FakePromptSession([KeyboardInterrupt(), '   ', 'edit-error', 'clip-error', 'clip-stop'])

    repl_mode._one_iteration(cli, repl_mode.ReplState())
    assert cli.query_history == []

    repl_mode._one_iteration(cli, repl_mode.ReplState())
    assert cli.query_history == []
    inputhook = cli.prompt_app.prompt_calls[-1]['inputhook']
    assert inputhook is not None
    inputhook(None)

    monkeypatch.setattr(repl_mode, 'handle_editor_command', lambda *args: (_ for _ in ()).throw(RuntimeError('edit boom')))
    repl_mode._one_iteration(cli, repl_mode.ReplState())
    assert 'edit boom' in cli.echo_calls[-1]

    monkeypatch.setattr(repl_mode, 'handle_editor_command', lambda mycli, text, inputhook, loaded_message_fn: text)
    monkeypatch.setattr(repl_mode, 'handle_clip_command', lambda mycli, text: (_ for _ in ()).throw(RuntimeError('clip boom')))
    repl_mode._one_iteration(cli, repl_mode.ReplState())
    assert 'clip boom' in cli.echo_calls[-1]

    monkeypatch.setattr(repl_mode, 'handle_clip_command', lambda mycli, text: True)
    repl_mode._one_iteration(cli, repl_mode.ReplState())
    assert cli.query_history == []


def test_one_iteration_covers_llm_paths(monkeypatch: pytest.MonkeyPatch) -> None:
    patch_repl_runtime_defaults(monkeypatch)
    click_output: list[str] = []
    monkeypatch.setattr(repl_mode.click, 'echo', lambda message='', **kwargs: click_output.append(str(message)))
    monkeypatch.setattr(repl_mode.special, 'is_timing_enabled', lambda: True)
    monkeypatch.setattr(repl_mode.special, 'is_llm_command', lambda text: text.startswith('\\llm'))

    class FakeSQLExecute:
        def __init__(self) -> None:
            self.dbname = 'db'
            self.conn = FakeConnection(cursor_value='cursor')

        def run(self, text: str) -> Iterator[SQLResult]:
            return iter([SQLResult(status=f'ran:{text}')])

    monkeypatch.setattr(
        repl_mode.special,
        'handle_llm',
        lambda text, cur, dbname, field_truncate, section_truncate: ('context', 'select 1', 1.25),
    )
    cli = make_repl_cli(FakeSQLExecute())
    cli.prompt_app = FakePromptSession(['\\llm ask', 'select 1'])
    repl_mode._one_iteration(
        cli,
        repl_mode.ReplState(),
    )
    assert click_output[:3] == ['LLM Response:', 'context', '---']
    assert cli.output_calls[0][0] == ['None', 'ran:select 1']

    cli_finish = make_repl_cli(FakeSQLExecute())
    cli_finish.prompt_app = FakePromptSession(['\\llm finish'])
    cli_finish.format_sqlresult = lambda result, **kwargs: iter([result.status_plain or 'row'])
    monkeypatch.setattr(
        repl_mode.special,
        'handle_llm',
        lambda *args, **kwargs: (_ for _ in ()).throw(repl_mode.special.FinishIteration(iter([SQLResult(status='done')]))),
    )
    repl_mode._one_iteration(cli_finish, repl_mode.ReplState())
    assert cli_finish.output_calls[0][0] == ['done']

    cli_empty = make_repl_cli(FakeSQLExecute())
    cli_empty.prompt_app = FakePromptSession(['\\llm empty'])
    monkeypatch.setattr(
        repl_mode.special,
        'handle_llm',
        lambda *args, **kwargs: (_ for _ in ()).throw(repl_mode.special.FinishIteration(None)),
    )
    repl_mode._one_iteration(cli_empty, repl_mode.ReplState())
    assert cli_empty.output_calls == []

    cli_err = make_repl_cli(FakeSQLExecute())
    cli_err.prompt_app = FakePromptSession(['\\llm err'])
    monkeypatch.setattr(
        repl_mode.special,
        'handle_llm',
        lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError('llm boom')),
    )
    repl_mode._one_iteration(cli_err, repl_mode.ReplState())
    assert 'llm boom' in cli_err.echo_calls[-1]

    cli_interrupt = make_repl_cli(FakeSQLExecute())
    cli_interrupt.prompt_app = FakePromptSession(['\\llm stop'])
    monkeypatch.setattr(
        repl_mode.special,
        'handle_llm',
        lambda *args, **kwargs: (_ for _ in ()).throw(KeyboardInterrupt()),
    )
    repl_mode._one_iteration(cli_interrupt, repl_mode.ReplState())
    assert cli_interrupt.output_calls == []

    cli_quiet = make_repl_cli(FakeSQLExecute())
    cli_quiet.prompt_app = FakePromptSession(['\\llm quiet', 'select 2'])
    monkeypatch.setattr(repl_mode.special, 'is_timing_enabled', lambda: False)
    monkeypatch.setattr(
        repl_mode.special,
        'handle_llm',
        lambda text, cur, dbname, field_truncate, section_truncate: ('', 'select 2', 0.5),
    )
    repl_mode._one_iteration(cli_quiet, repl_mode.ReplState())
    assert cli_quiet.output_calls[0][0] == ['None', 'ran:select 2']


def test_one_iteration_covers_redirect_destructive_success_refresh_and_logfile(monkeypatch: pytest.MonkeyPatch) -> None:
    patch_repl_runtime_defaults(monkeypatch)

    class FakeSQLExecute:
        def __init__(self) -> None:
            self.dbname: str | None = 'db'
            self.connection_id = 0
            self.calls: list[str] = []

        def connect(self) -> None:
            self.calls.append('connect')

        def run(self, text: str) -> Iterator[SQLResult]:
            self.calls.append(text)
            return iter([SQLResult(status='DROP 1')])

    sqlexecute = FakeSQLExecute()
    cli = make_repl_cli(sqlexecute)
    cli.logfile = False
    cli.destructive_warning = True
    monkeypatch.setattr(repl_mode, 'is_redirect_command', lambda text: text == 'redirect')
    monkeypatch.setattr(repl_mode, 'get_redirect_components', lambda text: ('dropdb', 'tee', '>', 'out.txt'))
    redirects: list[tuple[Any, ...]] = []
    monkeypatch.setattr(repl_mode.special, 'set_redirect', lambda *args: redirects.append(args))
    monkeypatch.setattr(
        repl_mode,
        'confirm_destructive_query',
        lambda keywords, text: None if text == 'dropdb' else (True if text == 'approved' else False),
    )
    monkeypatch.setattr(repl_mode, 'is_dropping_database', lambda text, dbname: text == 'dropdb')
    monkeypatch.setattr(repl_mode, 'need_completion_refresh', lambda text: text == 'dropdb')
    monkeypatch.setattr(repl_mode, 'need_completion_reset', lambda text: text == 'dropdb')
    monkeypatch.setattr(repl_mode, 'is_mutating', lambda status: True)

    repl_mode._one_iteration(cli, repl_mode.ReplState(), 'redirect')
    assert redirects == [('tee', '>', 'out.txt')]
    assert cli.refresh_calls == [True]
    assert cli.query_history[-1].query == 'dropdb'
    assert cli.query_history[-1].successful is True
    assert cli.query_history[-1].mutating is True
    assert sqlexecute.dbname is None
    assert sqlexecute.calls == ['dropdb', 'connect']
    assert 'Warning: This query was not logged.' in cli.echo_calls

    repl_mode._one_iteration(cli, repl_mode.ReplState(), 'approved')
    assert 'Your call!' in cli.echo_calls

    repl_mode._one_iteration(cli, repl_mode.ReplState(), 'denied')
    assert 'Wise choice!' in cli.echo_calls


def test_one_iteration_covers_reconnect_and_error_paths(monkeypatch: pytest.MonkeyPatch) -> None:
    patch_repl_runtime_defaults(monkeypatch)

    class InterfaceSQLExecute:
        def __init__(self) -> None:
            self.dbname: str | None = 'db'
            self.connection_id = 0
            self.calls: list[str] = []

        def run(self, text: str) -> Iterator[SQLResult]:
            self.calls.append(text)
            if text == 'iface' and self.calls.count('iface') == 1:
                raise pymysql.err.InterfaceError()
            return iter([SQLResult(status=f'ok:{text}')])

    interface_sql = InterfaceSQLExecute()
    cli_interface = make_repl_cli(interface_sql)
    interface_reconnect_calls: list[str] = []
    interface_results = iter([True])

    def interface_reconnect(database: str = '') -> bool:
        interface_reconnect_calls.append(database)
        return next(interface_results)

    cli_interface.reconnect = interface_reconnect

    repl_mode._one_iteration(cli_interface, repl_mode.ReplState(), 'iface')
    assert interface_sql.calls.count('iface') == 2
    assert cli_interface.query_history[-1].query == 'iface'
    assert interface_reconnect_calls == ['']

    cli_interface_false = make_repl_cli(InterfaceSQLExecute())
    false_calls: list[str] = []

    def interface_reconnect_false(database: str = '') -> bool:
        false_calls.append(database)
        return False

    cli_interface_false.reconnect = interface_reconnect_false
    repl_mode._one_iteration(cli_interface_false, repl_mode.ReplState(), 'iface')
    assert false_calls == ['']

    class ErrorSQLExecute:
        def __init__(self) -> None:
            self.dbname: str | None = 'db'
            self.connection_id = 0
            self.calls: list[str] = []

        def run(self, text: str) -> Iterator[SQLResult]:
            self.calls.append(text)
            if text == 'oplost' and self.calls.count('oplost') == 1:
                raise pymysql.OperationalError(2003, 'lost')
            if text == 'opbad':
                raise pymysql.OperationalError(9999, 'bad op')
            if text == 'nyi':
                raise NotImplementedError()
            if text == 'boom':
                raise RuntimeError('boom')
            if text == 'eof':
                raise EOFError()
            return iter([SQLResult(status=f'ok:{text}')])

    error_sql = ErrorSQLExecute()
    cli_error = make_repl_cli(error_sql)
    error_reconnect_calls: list[str] = []

    def error_reconnect(database: str = '') -> bool:
        error_reconnect_calls.append(database)
        return True

    cli_error.reconnect = error_reconnect

    repl_mode._one_iteration(cli_error, repl_mode.ReplState(), 'oplost')
    assert error_sql.calls.count('oplost') == 2
    repl_mode._one_iteration(cli_error, repl_mode.ReplState(), 'opbad')
    repl_mode._one_iteration(cli_error, repl_mode.ReplState(), 'nyi')
    repl_mode._one_iteration(cli_error, repl_mode.ReplState(), 'boom')
    assert any('bad op' in line for line in cli_error.echo_calls)
    assert 'Not Yet Implemented.' in cli_error.echo_calls
    assert any('boom' in line for line in cli_error.echo_calls)
    assert error_reconnect_calls == ['']

    cli_error_false = make_repl_cli(ErrorSQLExecute())
    false_reconnect_calls: list[str] = []

    def error_reconnect_false(database: str = '') -> bool:
        false_reconnect_calls.append(database)
        return False

    cli_error_false.reconnect = error_reconnect_false
    repl_mode._one_iteration(cli_error_false, repl_mode.ReplState(), 'oplost')
    assert false_reconnect_calls == ['']

    with pytest.raises(EOFError):
        repl_mode._one_iteration(cli_error, repl_mode.ReplState(), 'eof')


def test_one_iteration_reraises_eoferror(monkeypatch: pytest.MonkeyPatch) -> None:
    patch_repl_runtime_defaults(monkeypatch)

    class EofSQLExecute:
        dbname = 'db'
        connection_id = 0

        def run(self, text: str) -> Iterator[SQLResult]:
            raise EOFError()

    with pytest.raises(EOFError):
        repl_mode._one_iteration(make_repl_cli(EofSQLExecute()), repl_mode.ReplState(), 'eof')


def test_one_iteration_covers_cancel_paths_and_redirect_error(monkeypatch: pytest.MonkeyPatch) -> None:
    patch_repl_runtime_defaults(monkeypatch)

    class FakeSQLExecute:
        def __init__(self) -> None:
            self.dbname = 'db'
            self.connection_id = 0

        def connect(self) -> None:
            return None

        def run(self, text: str) -> Iterator[SQLResult]:
            if text == 'cancel-ok':
                self.connection_id = 7
                raise KeyboardInterrupt()
            if text == 'kill 7':
                return iter([SQLResult(status='OK')])
            if text == 'cancel-fail':
                self.connection_id = 8
                raise KeyboardInterrupt()
            if text == 'kill 8':
                return iter([SQLResult(status='failed')])
            if text == 'cancel-error':
                self.connection_id = 9
                raise KeyboardInterrupt()
            if text == 'kill 9':
                raise RuntimeError('kill failed')
            if text == 'cancel-missing':
                self.connection_id = 0
                raise KeyboardInterrupt()
            return iter([SQLResult(status='ok')])

    cli = make_repl_cli(FakeSQLExecute())
    monkeypatch.setattr(repl_mode, 'is_redirect_command', lambda text: text == 'redirect-bad')
    monkeypatch.setattr(repl_mode, 'get_redirect_components', lambda text: ('sql', 'tee', '>', 'out.txt'))
    monkeypatch.setattr(repl_mode.special, 'set_redirect', lambda *args: (_ for _ in ()).throw(RuntimeError('redirect boom')))
    repl_mode._one_iteration(cli, repl_mode.ReplState(), 'redirect-bad')
    assert 'redirect boom' in cli.echo_calls[-1]

    repl_mode._one_iteration(cli, repl_mode.ReplState(), 'cancel-ok')
    repl_mode._one_iteration(cli, repl_mode.ReplState(), 'cancel-fail')
    repl_mode._one_iteration(cli, repl_mode.ReplState(), 'cancel-error')
    repl_mode._one_iteration(cli, repl_mode.ReplState(), 'cancel-missing')
    assert 'Cancelled query id: 7' in cli.echo_calls
    assert any('Failed to confirm query cancellation' in line for line in cli.echo_calls)
    assert any('Encountered error while cancelling query' in line for line in cli.echo_calls)
    assert 'Did not get a connection id, skip cancelling query' in cli.echo_calls


def test_main_repl_covers_setup_loop_and_goodbye(monkeypatch: pytest.MonkeyPatch) -> None:
    cli = make_repl_cli(SimpleNamespace())
    cli.less_chatty = False
    cli.smart_completion = True
    loop_iterations: list[int] = []
    monkeypatch.setattr(repl_mode, '_create_history', lambda mycli: 'history')
    monkeypatch.setattr(repl_mode, 'mycli_bindings', lambda mycli: 'bindings')
    monkeypatch.setattr(repl_mode, '_show_startup_banner', lambda mycli, sqlexecute: None)
    monkeypatch.setattr(
        repl_mode,
        '_build_prompt_session',
        lambda mycli, state, history, key_bindings: setattr(mycli, 'prompt_app', FakePromptSession()),
    )

    def fake_one_iteration(mycli: Any, state: repl_mode.ReplState) -> None:
        loop_iterations.append(state.iterations)
        if len(loop_iterations) == 2:
            raise EOFError()

    closed: list[bool] = []
    monkeypatch.setattr(repl_mode, '_one_iteration', fake_one_iteration)
    monkeypatch.setattr(repl_mode.special, 'close_tee', lambda: closed.append(True))

    repl_mode.main_repl(cli)

    assert cli.pager_configured == 1
    assert cli.refresh_calls == [False]
    assert cli.title_calls == 1
    assert loop_iterations == [0, 1]
    assert closed == [True]
    assert cli.echo_calls[-1] == 'Goodbye!'


def test_main_repl_covers_no_refresh_and_quiet_exit(monkeypatch: pytest.MonkeyPatch) -> None:
    cli = make_repl_cli(SimpleNamespace())
    cli.less_chatty = True
    cli.smart_completion = False
    monkeypatch.setattr(repl_mode, '_create_history', lambda mycli: 'history')
    monkeypatch.setattr(repl_mode, 'mycli_bindings', lambda mycli: 'bindings')
    monkeypatch.setattr(repl_mode, '_show_startup_banner', lambda mycli, sqlexecute: None)
    monkeypatch.setattr(
        repl_mode,
        '_build_prompt_session',
        lambda mycli, state, history, key_bindings: setattr(mycli, 'prompt_app', FakePromptSession()),
    )
    monkeypatch.setattr(repl_mode, '_one_iteration', lambda mycli, state: (_ for _ in ()).throw(EOFError()))
    monkeypatch.setattr(repl_mode.special, 'close_tee', lambda: None)

    repl_mode.main_repl(cli)

    assert cli.refresh_calls == []
    assert cli.echo_calls == []


def test_output_results_covers_remaining_watch_select_and_warning_branches(monkeypatch: pytest.MonkeyPatch) -> None:
    class WarninglessSQLExecute:
        def run(self, text: str) -> list[SQLResult]:
            assert text == 'SHOW WARNINGS'
            return []

    cli = make_repl_cli(WarninglessSQLExecute())
    cli.show_warnings = True
    cli.auto_vertical_output = False
    cli.prompt_app = FakePromptSession(columns=77)
    monkeypatch.setattr(repl_mode, 'Cursor', FakeCursorBase)
    monkeypatch.setattr(repl_mode, 'is_mutating', lambda status: False)
    monkeypatch.setattr(repl_mode, 'confirm', lambda text: True)
    monkeypatch.setattr(repl_mode.special, 'is_expanded_output', lambda: False)
    monkeypatch.setattr(repl_mode.special, 'is_redirected', lambda: False)
    monkeypatch.setattr(repl_mode.special, 'is_timing_enabled', lambda: True)
    monkeypatch.setattr(repl_mode, 'is_select', lambda status: status == 'select')
    monkeypatch.setattr(repl_mode.time, 'time', lambda: 0.0)

    repl_mode._output_results(
        cli,
        repl_mode.ReplState(),
        sqlresult_generator(
            SQLResult(status='watch', command={'name': 'watch', 'seconds': '1'}),
            SQLResult(status='watch', command={'name': 'watch', 'seconds': '2'}),
            SQLResult(status='select', rows=cast(Any, FakeCursorBase(rowcount=1001, warning_count=1))),
        ),
        start=0.0,
    )
    assert cli.output_calls
