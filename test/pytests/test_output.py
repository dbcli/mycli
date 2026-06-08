from __future__ import annotations

import itertools
import shutil
from types import SimpleNamespace
from typing import Any, cast

import click
from configobj import ConfigObj
import prompt_toolkit
from prompt_toolkit.formatted_text import ANSI, FormattedText, to_plain_text
import pytest

from mycli import output as output_module
from mycli.output import OutputMixin
from mycli.packages.sqlresult import SQLResult
from test.utils import DummyFormatter, FakeCursorBase, make_bare_mycli  # type: ignore[attr-defined]


def test_output_timing_logs_and_prints_with_default_style(monkeypatch: pytest.MonkeyPatch) -> None:
    cli = make_bare_mycli()
    logged: list[Any] = []
    printed: list[tuple[Any, Any]] = []
    cli.log_output = lambda value: logged.append(value)  # type: ignore[assignment]
    monkeypatch.setattr(prompt_toolkit, 'print_formatted_text', lambda text, style=None: printed.append((text, style)))

    OutputMixin.output_timing(cli, '0.12 sec')

    assert logged == ['0.12 sec']
    assert to_plain_text(printed[0][0]) == '0.12 sec'
    assert list(printed[0][0])[0][0].strip() == 'class:output.timing'
    assert printed[0][1] == cli.ptoolkit_style


def test_output_timing_uses_warning_style(monkeypatch: pytest.MonkeyPatch) -> None:
    cli = make_bare_mycli()
    cli.log_output = lambda value: None  # type: ignore[assignment]
    printed: list[Any] = []
    monkeypatch.setattr(prompt_toolkit, 'print_formatted_text', lambda text, style=None: printed.append(text))

    OutputMixin.output_timing(cli, '0.34 sec', is_warnings_style=True)

    assert list(printed[0])[0][0].strip() == 'class:warnings.timing'


def test_log_query_and_log_output_write_plain_text(tmp_path) -> None:
    cli = make_bare_mycli()
    logfile = tmp_path / 'audit.log'

    with logfile.open('w+', encoding='utf-8') as handle:
        cli.logfile = handle
        OutputMixin.log_query(cli, 'select 1')
        OutputMixin.log_output(cli, ANSI('\x1b[31mhello\x1b[0m'))
        handle.seek(0)
        contents = handle.read()

    assert 'select 1' in contents
    assert 'hello' in contents
    assert '\x1b[31m' not in contents


def test_log_output_ignores_missing_logfile() -> None:
    cli = make_bare_mycli()
    cli.logfile = None

    OutputMixin.log_output(cli, 'nothing to write')


def test_echo_logs_and_prints(monkeypatch: pytest.MonkeyPatch) -> None:
    cli = make_bare_mycli()
    logged: list[str] = []
    printed: list[tuple[str, dict[str, Any]]] = []
    cli.log_output = lambda value: logged.append(value)  # type: ignore[assignment]
    monkeypatch.setattr(click, 'secho', lambda value, **kwargs: printed.append((value, kwargs)))

    OutputMixin.echo(cli, 'message', fg='red')

    assert logged == ['message']
    assert printed == [('message', {'fg': 'red'})]


def test_get_output_margin_renders_prompt_once_and_counts_status_lines(monkeypatch: pytest.MonkeyPatch) -> None:
    cli = make_bare_mycli()
    cli.prompt_lines = 0
    cli.prompt_format = 'ignored'
    cli.prompt_session = None
    cli.get_reserved_space = lambda: 2  # type: ignore[assignment]
    monkeypatch.setattr(output_module.repl_mode, 'render_prompt_string', lambda *_args: FormattedText([('', 'one\ntwo')]))
    monkeypatch.setattr(output_module.special, 'is_timing_enabled', lambda: True)

    margin = OutputMixin.get_output_margin(cli, 'ok\nwarning')

    assert margin == 7
    assert cli.prompt_lines == 2


def test_get_output_margin_uses_prompt_session_render_counter(monkeypatch: pytest.MonkeyPatch) -> None:
    cli = make_bare_mycli()
    cli.prompt_lines = 0
    cli.prompt_session = cast(Any, SimpleNamespace(app=SimpleNamespace(render_counter=9)))
    cli.get_reserved_space = lambda: 1  # type: ignore[assignment]
    render_counters: list[int] = []

    def render_prompt_string(_cli: Any, _prompt_format: str, render_counter: int) -> FormattedText:
        render_counters.append(render_counter)
        return FormattedText([('', 'prompt')])

    monkeypatch.setattr(output_module.repl_mode, 'render_prompt_string', render_prompt_string)
    monkeypatch.setattr(output_module.special, 'is_timing_enabled', lambda: False)

    assert OutputMixin.get_output_margin(cli) == 2
    assert render_counters == [9]


def test_output_writes_lines_sinks_and_status(monkeypatch: pytest.MonkeyPatch) -> None:
    cli = make_bare_mycli()
    cli.prompt_session = None
    cli.explicit_pager = False
    cli.get_output_margin = lambda status=None: 1  # type: ignore[assignment]
    logged: list[Any] = []
    tee: list[str] = []
    once: list[str] = []
    pipe_once: list[str] = []
    printed_lines: list[str] = []
    printed_status: list[Any] = []
    cli.log_output = lambda value: logged.append(value)  # type: ignore[assignment]
    monkeypatch.setattr(output_module.special, 'write_tee', lambda value: tee.append(value))
    monkeypatch.setattr(output_module.special, 'write_once', lambda value: once.append(value))
    monkeypatch.setattr(output_module.special, 'write_pipe_once', lambda value: pipe_once.append(value))
    monkeypatch.setattr(output_module.special, 'is_redirected', lambda: False)
    monkeypatch.setattr(output_module.special, 'is_pager_enabled', lambda: False)
    monkeypatch.setattr(click, 'secho', lambda value, **_kwargs: printed_lines.append(value))
    monkeypatch.setattr(prompt_toolkit, 'print_formatted_text', lambda text, style=None: printed_status.append(text))

    OutputMixin.output(cli, itertools.chain(['row 1', 'row 2']), SQLResult(status='done'))

    assert logged == ['row 1', 'row 2', 'done']
    assert tee == ['row 1', 'row 2']
    assert once == ['row 1', 'row 2']
    assert pipe_once == ['row 1', 'row 2']
    assert printed_lines == ['row 1', 'row 2']
    assert to_plain_text(printed_status[0]) == 'done'
    assert list(printed_status[0])[0][0].strip() == 'class:output.status'


def test_output_uses_prompt_session_size(monkeypatch: pytest.MonkeyPatch) -> None:
    cli = make_bare_mycli()
    cli.prompt_session = cast(
        Any,
        SimpleNamespace(output=SimpleNamespace(get_size=lambda: SimpleNamespace(columns=80, rows=24))),
    )
    cli.explicit_pager = False
    cli.log_output = lambda value: None  # type: ignore[assignment]
    cli.get_output_margin = lambda status=None: 1  # type: ignore[assignment]
    printed_lines: list[str] = []
    monkeypatch.setattr(output_module.special, 'write_tee', lambda value: None)
    monkeypatch.setattr(output_module.special, 'write_once', lambda value: None)
    monkeypatch.setattr(output_module.special, 'write_pipe_once', lambda value: None)
    monkeypatch.setattr(output_module.special, 'is_redirected', lambda: False)
    monkeypatch.setattr(output_module.special, 'is_pager_enabled', lambda: False)
    monkeypatch.setattr(click, 'secho', lambda value, **_kwargs: printed_lines.append(value))

    OutputMixin.output(cli, itertools.chain(['row']), SQLResult())

    assert printed_lines == ['row']


def test_output_flushes_buffer_when_content_does_not_fit(monkeypatch: pytest.MonkeyPatch) -> None:
    cli = make_bare_mycli()
    cli.prompt_session = None
    cli.explicit_pager = False
    cli.log_output = lambda value: None  # type: ignore[assignment]
    cli.get_output_margin = lambda status=None: output_module.DEFAULT_HEIGHT  # type: ignore[assignment]
    printed_lines: list[str] = []
    monkeypatch.setattr(output_module.special, 'write_tee', lambda value: None)
    monkeypatch.setattr(output_module.special, 'write_once', lambda value: None)
    monkeypatch.setattr(output_module.special, 'write_pipe_once', lambda value: None)
    monkeypatch.setattr(output_module.special, 'is_redirected', lambda: False)
    monkeypatch.setattr(output_module.special, 'is_pager_enabled', lambda: False)
    monkeypatch.setattr(click, 'secho', lambda value, **_kwargs: printed_lines.append(value))

    OutputMixin.output(cli, itertools.chain(['row 1', 'row 2']), SQLResult())

    assert printed_lines == ['row 1', 'row 2']


def test_output_switches_to_pager_when_content_does_not_fit(monkeypatch: pytest.MonkeyPatch) -> None:
    cli = make_bare_mycli()
    cli.prompt_session = None
    cli.explicit_pager = False
    cli.log_output = lambda value: None  # type: ignore[assignment]
    cli.get_output_margin = lambda status=None: output_module.DEFAULT_HEIGHT  # type: ignore[assignment]
    paged_lines: list[str] = []
    monkeypatch.setattr(output_module.special, 'write_tee', lambda value: None)
    monkeypatch.setattr(output_module.special, 'write_once', lambda value: None)
    monkeypatch.setattr(output_module.special, 'write_pipe_once', lambda value: None)
    monkeypatch.setattr(output_module.special, 'is_redirected', lambda: False)
    monkeypatch.setattr(output_module.special, 'is_pager_enabled', lambda: True)
    monkeypatch.setattr(click, 'echo_via_pager', lambda values: paged_lines.extend(list(values)))

    OutputMixin.output(cli, itertools.chain(['row']), SQLResult())

    assert paged_lines == ['row\n']


def test_output_redirected_skips_screen_printing(monkeypatch: pytest.MonkeyPatch) -> None:
    cli = make_bare_mycli()
    cli.prompt_session = None
    cli.log_output = lambda value: None  # type: ignore[assignment]
    cli.get_output_margin = lambda status=None: 1  # type: ignore[assignment]
    printed_lines: list[str] = []
    monkeypatch.setattr(output_module.special, 'write_tee', lambda value: None)
    monkeypatch.setattr(output_module.special, 'write_once', lambda value: None)
    monkeypatch.setattr(output_module.special, 'write_pipe_once', lambda value: None)
    monkeypatch.setattr(output_module.special, 'is_redirected', lambda: True)
    monkeypatch.setattr(output_module.special, 'is_pager_enabled', lambda: False)
    monkeypatch.setattr(click, 'secho', lambda value, **_kwargs: printed_lines.append(value))

    OutputMixin.output(cli, itertools.chain(['row']), SQLResult())

    assert printed_lines == []


def test_output_uses_warning_status_style(monkeypatch: pytest.MonkeyPatch) -> None:
    cli = make_bare_mycli()
    cli.log_output = lambda value: None  # type: ignore[assignment]
    cli.get_output_margin = lambda status=None: 1  # type: ignore[assignment]
    printed_status: list[Any] = []
    monkeypatch.setattr(prompt_toolkit, 'print_formatted_text', lambda text, style=None: printed_status.append(text))

    OutputMixin.output(cli, itertools.chain([]), SQLResult(status='warning'), is_warnings_style=True)

    assert list(printed_status[0])[0][0].strip() == 'class:warnings.status'


def test_output_preserves_formatted_status(monkeypatch: pytest.MonkeyPatch) -> None:
    cli = make_bare_mycli()
    cli.log_output = lambda value: None  # type: ignore[assignment]
    cli.get_output_margin = lambda status=None: 1  # type: ignore[assignment]
    printed_status: list[Any] = []
    monkeypatch.setattr(prompt_toolkit, 'print_formatted_text', lambda text, style=None: printed_status.append(text))
    status = FormattedText([('class:custom', 'formatted')])

    OutputMixin.output(cli, itertools.chain([]), SQLResult(status=status))

    assert to_plain_text(printed_status[0]) == 'formatted'


def test_output_sends_buffer_to_pager_when_pager_is_explicit(monkeypatch: pytest.MonkeyPatch) -> None:
    cli = make_bare_mycli()
    cli.prompt_session = None
    cli.explicit_pager = True
    cli.log_output = lambda value: None  # type: ignore[assignment]
    cli.get_output_margin = lambda status=None: 1  # type: ignore[assignment]
    paged_lines: list[str] = []
    monkeypatch.setattr(output_module.special, 'write_tee', lambda value: None)
    monkeypatch.setattr(output_module.special, 'write_once', lambda value: None)
    monkeypatch.setattr(output_module.special, 'write_pipe_once', lambda value: None)
    monkeypatch.setattr(output_module.special, 'is_redirected', lambda: False)
    monkeypatch.setattr(output_module.special, 'is_pager_enabled', lambda: True)
    monkeypatch.setattr(click, 'echo_via_pager', lambda values: paged_lines.extend(list(values)))
    monkeypatch.setattr(prompt_toolkit, 'print_formatted_text', lambda text, style=None: None)

    OutputMixin.output(cli, itertools.chain(['row 1', 'row 2']), SQLResult())

    assert paged_lines == ['row 1\n', 'row 2\n']


def test_configure_pager_uses_more_for_missing_less_on_windows(monkeypatch: pytest.MonkeyPatch) -> None:
    cli = make_bare_mycli()
    cli.my_cnf = ConfigObj({'client': {'pager': 'less'}})
    cli.config = ConfigObj({'main': {'pager': '', 'enable_pager': 'True'}})
    cli.read_my_cnf = lambda cnf, keys: {'pager': 'less', 'skip-pager': None}  # type: ignore[assignment]
    pager_calls: list[str] = []
    monkeypatch.setattr(output_module, 'WIN', True)
    monkeypatch.setattr(output_module.shutil, 'which', lambda value: None)
    monkeypatch.setattr(output_module.special, 'set_pager', lambda value: pager_calls.append(value))
    monkeypatch.setattr(output_module.special, 'disable_pager', lambda: None)

    OutputMixin.configure_pager(cli)

    assert pager_calls == ['more']


def test_configure_pager_prefers_my_cnf_pager_and_sets_less(monkeypatch: pytest.MonkeyPatch) -> None:
    cli = make_bare_mycli()
    cli.my_cnf = ConfigObj({'client': {'pager': 'my-pager'}})
    cli.config = ConfigObj({'main': {'pager': 'config-pager', 'enable_pager': 'True'}})
    cli.read_my_cnf = lambda cnf, keys: {'pager': 'my-pager', 'skip-pager': None}  # type: ignore[assignment]
    pager_calls: list[str] = []
    disabled: list[bool] = []
    monkeypatch.delenv('LESS', raising=False)
    monkeypatch.setattr(output_module.special, 'set_pager', lambda value: pager_calls.append(value))
    monkeypatch.setattr(output_module.special, 'disable_pager', lambda: disabled.append(True))

    OutputMixin.configure_pager(cli)

    assert pager_calls == ['my-pager']
    assert disabled == []
    assert cli.explicit_pager is True
    assert output_module.os.environ['LESS'] == '-RXF'


def test_configure_pager_disables_when_skip_pager_is_set(monkeypatch: pytest.MonkeyPatch) -> None:
    cli = make_bare_mycli()
    cli.my_cnf = ConfigObj({'client': {}})
    cli.config = ConfigObj({'main': {'pager': '', 'enable_pager': 'True'}})
    cli.read_my_cnf = lambda cnf, keys: {'pager': None, 'skip-pager': '1'}  # type: ignore[assignment]
    disabled: list[bool] = []
    monkeypatch.setattr(output_module.special, 'set_pager', lambda value: None)
    monkeypatch.setattr(output_module.special, 'disable_pager', lambda: disabled.append(True))

    OutputMixin.configure_pager(cli)

    assert cli.explicit_pager is False
    assert disabled == [True]


def test_format_sqlresult_uses_redirect_formatter_and_appends_preamble_postamble() -> None:
    cli = make_bare_mycli()
    cli.main_formatter = DummyFormatter()
    cli.redirect_formatter = DummyFormatter()
    result = SQLResult(preamble='before', header=['id'], rows=[(1,)], postamble='after')

    formatted = list(OutputMixin.format_sqlresult(cli, result, is_redirected=True))

    assert formatted == ['before', 'plain output', 'after']
    assert cli.main_formatter.calls == []
    assert cli.redirect_formatter.calls


def test_format_sqlresult_uses_null_string_when_default_missing_value_is_configured() -> None:
    cli = make_bare_mycli()
    cli.main_formatter = DummyFormatter()
    result = SQLResult(header=['id'], rows=[(None,)])

    list(OutputMixin.format_sqlresult(cli, result, null_string='<null>'))

    _, kwargs = cli.main_formatter.calls[-1]
    assert kwargs['missing_value'] == '<null>'


def test_format_sqlresult_for_cursor_sets_column_types_and_alignment(monkeypatch: pytest.MonkeyPatch) -> None:
    cli = make_bare_mycli()
    cli.main_formatter = DummyFormatter()
    monkeypatch.setattr(output_module, 'Cursor', FakeCursorBase)
    rows = FakeCursorBase(rows=[(1, 'name')], rowcount=1, description=[('id', 3), ('name', 253)])
    result = SQLResult(header=['id', 'name'], rows=cast(Any, rows))

    assert list(OutputMixin.format_sqlresult(cli, result, numeric_alignment='left')) == ['plain output']

    _, kwargs = cli.main_formatter.calls[-1]
    assert kwargs['column_types'] == [int, str]
    assert kwargs['colalign'] == ['left', 'left']


def test_format_sqlresult_for_empty_cursor_uses_empty_column_metadata(monkeypatch: pytest.MonkeyPatch) -> None:
    cli = make_bare_mycli()
    cli.main_formatter = DummyFormatter()
    monkeypatch.setattr(output_module, 'Cursor', FakeCursorBase)
    rows = FakeCursorBase(rowcount=0, description=[('id', 3)])
    result = SQLResult(header=['id'], rows=cast(Any, rows))

    list(OutputMixin.format_sqlresult(cli, result))

    _, kwargs = cli.main_formatter.calls[-1]
    assert kwargs['column_types'] == []
    assert kwargs['colalign'] == []


def test_format_sqlresult_materializes_cursor_rows_when_width_is_limited(monkeypatch: pytest.MonkeyPatch) -> None:
    cli = make_bare_mycli()
    cli.main_formatter = DummyFormatter()
    monkeypatch.setattr(output_module, 'Cursor', FakeCursorBase)
    rows = FakeCursorBase(rows=[(1,)], rowcount=1, description=[('id', 3)])
    result = SQLResult(header=['id'], rows=cast(Any, rows))

    list(OutputMixin.format_sqlresult(cli, result, max_width=100))

    formatted_rows = cli.main_formatter.calls[-1][0][0]
    assert formatted_rows == [(1,)]


def test_format_sqlresult_splits_string_formatter_output() -> None:
    cli = make_bare_mycli()
    cli.main_formatter = DummyFormatter()
    cli.main_formatter.format_output = lambda *args, **kwargs: 'one\ntwo'  # type: ignore[method-assign]
    result = SQLResult(header=['id'], rows=[(1,)])

    assert list(OutputMixin.format_sqlresult(cli, result)) == ['one', 'two']


def test_format_sqlresult_switches_to_vertical_when_first_line_is_too_wide() -> None:
    cli = make_bare_mycli()
    cli.main_formatter = DummyFormatter()
    result = SQLResult(header=['id'], rows=[(1,)])

    assert list(OutputMixin.format_sqlresult(cli, result, max_width=2)) == ['vertical output']


def test_format_sqlresult_splits_string_vertical_output_when_table_is_too_wide() -> None:
    cli = make_bare_mycli()
    cli.main_formatter = DummyFormatter()

    def format_output(rows, header, format_name=None, **kwargs):
        if format_name == 'vertical':
            return 'vertical one\nvertical two'
        return ['too wide']

    cli.main_formatter.format_output = format_output  # type: ignore[method-assign]
    result = SQLResult(header=['id'], rows=[(1,)])

    assert list(OutputMixin.format_sqlresult(cli, result, max_width=2)) == ['vertical one', 'vertical two']


def test_format_sqlresult_keeps_table_when_first_line_fits_width() -> None:
    cli = make_bare_mycli()
    cli.main_formatter = DummyFormatter()
    result = SQLResult(header=['id'], rows=[(1,)])

    assert list(OutputMixin.format_sqlresult(cli, result, max_width=100)) == ['plain output']


def test_get_reserved_space_caps_ratio(monkeypatch: pytest.MonkeyPatch) -> None:
    cli = make_bare_mycli()
    monkeypatch.setattr(shutil, 'get_terminal_size', lambda *args, **kwargs: (120, 40))

    assert OutputMixin.get_reserved_space(cli) == 8
