from types import SimpleNamespace
from typing import Any, cast

from mycli import client_query, main
from mycli.packages.sqlresult import SQLResult
from mycli.types import Query
from test.utils import (  # type: ignore[attr-defined]
    FakeCursorBase,
    ReusableLock,
    make_bare_mycli,
)


def make_refresh_cli() -> tuple[Any, dict[str, Any]]:
    cli = make_bare_mycli()
    state: dict[str, Any] = {
        'stopped': [],
        'refresh_calls': [],
        'set_dbname_calls': [],
    }
    callback = object()
    cli.schema_prefetcher = SimpleNamespace(stop=lambda: state['stopped'].append(True))
    cli.sqlexecute = SimpleNamespace(dbname='current')
    cli._on_completions_refreshed = callback
    cli.completer = SimpleNamespace(
        keyword_casing='upper',
        set_dbname=lambda dbname: state['set_dbname_calls'].append(dbname),
    )
    cli.main_formatter = SimpleNamespace(supported_formats=['ascii', 'csv'])
    cli.completion_refresher = SimpleNamespace(
        refresh=lambda executor, callbacks, options: state['refresh_calls'].append((executor, callbacks, options))
    )
    cli.smart_completion = True
    state['callback'] = callback
    return cli, state


def test_refresh_completions_stops_prefetch() -> None:
    cli, state = make_refresh_cli()

    main.MyCli.refresh_completions(cli)

    assert state['stopped'] == [True]


def test_refresh_completions_returns_started_status() -> None:
    cli, _state = make_refresh_cli()

    result: list[SQLResult] = main.MyCli.refresh_completions(cli)

    assert result == [SQLResult(status='Auto-completion refresh started in the background.')]


def test_refresh_completions_passes_options_to_refresher() -> None:
    cli, state = make_refresh_cli()

    main.MyCli.refresh_completions(cli)

    assert state['refresh_calls'] == [
        (
            cli.sqlexecute,
            state['callback'],
            {
                'smart_completion': True,
                'supported_formats': ['ascii', 'csv'],
                'keyword_casing': 'upper',
            },
        )
    ]


def test_refresh_completions_does_not_update_dbname_without_reset() -> None:
    cli, state = make_refresh_cli()

    main.MyCli.refresh_completions(cli)

    assert state['set_dbname_calls'] == []


def test_refresh_completions_updates_dbname_when_reset() -> None:
    cli = make_bare_mycli()
    set_dbname_calls: list[str] = []
    cli.schema_prefetcher = SimpleNamespace(stop=lambda: None)
    cli.sqlexecute = SimpleNamespace(dbname='next_db')
    cli.completer = SimpleNamespace(keyword_casing='lower', set_dbname=lambda dbname: set_dbname_calls.append(dbname))
    cli.main_formatter = SimpleNamespace(supported_formats=['table'])
    cli.completion_refresher = SimpleNamespace(refresh=lambda executor, callbacks, options: None)

    main.MyCli.refresh_completions(cli, reset=True)

    assert set_dbname_calls == ['next_db']


def test_refresh_completions_uses_lock_when_reset() -> None:
    cli = make_bare_mycli()
    entered_lock = {'count': 0}
    cli.schema_prefetcher = SimpleNamespace(stop=lambda: None)
    cli.sqlexecute = SimpleNamespace(dbname='next_db')
    cli._completer_lock = cast(Any, ReusableLock(lambda: entered_lock.__setitem__('count', entered_lock['count'] + 1)))
    cli.completer = SimpleNamespace(keyword_casing='lower', set_dbname=lambda dbname: None)
    cli.main_formatter = SimpleNamespace(supported_formats=['table'])
    cli.completion_refresher = SimpleNamespace(refresh=lambda executor, callbacks, options: None)

    main.MyCli.refresh_completions(cli, reset=True)

    assert entered_lock == {'count': 1}


def make_refreshed_cli() -> tuple[Any, Any, Any, dict[str, Any]]:
    cli = make_bare_mycli()
    state: dict[str, Any] = {
        'entered_lock': {'count': 0},
        'invalidated': [],
        'prefetch_started': [],
        'copy_calls': [],
    }
    old_completer = SimpleNamespace(dbmetadata={'old': object()})
    new_completer = SimpleNamespace(
        dbname='current',
        copy_other_schemas_from=lambda source, exclude: state['copy_calls'].append((source, exclude)),
    )
    cli._completer_lock = cast(
        Any,
        ReusableLock(lambda: state['entered_lock'].__setitem__('count', state['entered_lock']['count'] + 1)),
    )
    cli.completer = old_completer
    cli.prompt_session = SimpleNamespace(app=SimpleNamespace(invalidate=lambda: state['invalidated'].append(True)))
    cli.schema_prefetcher = SimpleNamespace(start_configured=lambda: state['prefetch_started'].append(True))
    return cli, old_completer, new_completer, state


def test_on_completions_refreshed_swaps_completer() -> None:
    cli, _old_completer, new_completer, _state = make_refreshed_cli()

    main.MyCli._on_completions_refreshed(cli, new_completer)

    assert cli.completer is new_completer


def test_on_completions_refreshed_copies_other_schemas() -> None:
    cli, old_completer, new_completer, state = make_refreshed_cli()

    main.MyCli._on_completions_refreshed(cli, new_completer)

    assert state['copy_calls'] == [(old_completer, 'current')]


def test_on_completions_refreshed_uses_lock() -> None:
    cli, _old_completer, new_completer, state = make_refreshed_cli()

    main.MyCli._on_completions_refreshed(cli, new_completer)

    assert state['entered_lock'] == {'count': 1}


def test_on_completions_refreshed_invalidates_prompt() -> None:
    cli, _old_completer, new_completer, state = make_refreshed_cli()

    main.MyCli._on_completions_refreshed(cli, new_completer)

    assert state['invalidated'] == [True]


def test_on_completions_refreshed_starts_schema_prefetch() -> None:
    cli, _old_completer, new_completer, state = make_refreshed_cli()

    main.MyCli._on_completions_refreshed(cli, new_completer)

    assert state['prefetch_started'] == [True]


def run_query_with_state(monkeypatch, tmp_path, *, warnings_enabled: bool = True) -> dict[str, Any]:
    cli = make_bare_mycli()
    normal_rows = FakeCursorBase(rows=[('one',)], warning_count=1)
    warning_rows = FakeCursorBase(rows=[('warning',)], warning_count=0)
    state: dict[str, Any] = {
        'run_calls': [],
        'logged_queries': [],
        'logged_output': [],
        'formatted': [],
        'echoed': [],
        'checkpoint_path': tmp_path / 'checkpoint.sql',
    }

    def run(sql: str) -> list[SQLResult]:
        state['run_calls'].append(sql)
        if sql == 'SHOW WARNINGS':
            return [SQLResult(rows=warning_rows, status='warnings')]
        return [SQLResult(rows=normal_rows, status='ok')]

    def format_sqlresult(result: SQLResult, **kwargs: Any) -> list[str]:
        state['formatted'].append((result, kwargs))
        return [str(result.status)]

    monkeypatch.setattr(client_query, 'Cursor', FakeCursorBase)
    monkeypatch.setattr(client_query.special, 'is_expanded_output', lambda: True)
    monkeypatch.setattr(client_query.special, 'is_redirected', lambda: False)
    monkeypatch.setattr(client_query.special, 'is_show_warnings_enabled', lambda: warnings_enabled)
    monkeypatch.setattr(client_query.click, 'echo', lambda line, nl=True: state['echoed'].append((line, nl)))

    cli.sqlexecute = SimpleNamespace(run=run)
    cli.log_query = lambda query: state['logged_queries'].append(query)
    cli.log_output = lambda line: state['logged_output'].append(line)
    cli.format_sqlresult = format_sqlresult
    main.MyCli.run_query(cli, 'select 1;\n', checkpoint=str(state['checkpoint_path']), new_line=False)
    state['cli'] = cli
    return state


def test_run_query_executes_query(monkeypatch, tmp_path) -> None:
    state = run_query_with_state(monkeypatch, tmp_path, warnings_enabled=False)

    assert state['run_calls'] == ['select 1;\n']


def test_run_query_logs_query(monkeypatch, tmp_path) -> None:
    state = run_query_with_state(monkeypatch, tmp_path, warnings_enabled=False)

    assert state['logged_queries'] == ['select 1;\n']


def test_run_query_logs_output(monkeypatch, tmp_path) -> None:
    state = run_query_with_state(monkeypatch, tmp_path, warnings_enabled=False)

    assert state['logged_output'] == ['ok']


def test_run_query_echoes_output(monkeypatch, tmp_path) -> None:
    state = run_query_with_state(monkeypatch, tmp_path, warnings_enabled=False)

    assert state['echoed'] == [('ok', False)]


def test_run_query_sets_formatter_query(monkeypatch, tmp_path) -> None:
    state = run_query_with_state(monkeypatch, tmp_path, warnings_enabled=False)
    cli = state['cli']

    assert (cli.main_formatter.query, cli.redirect_formatter.query) == ('select 1;\n', 'select 1;\n')


def test_run_query_passes_display_flags_to_formatter(monkeypatch, tmp_path) -> None:
    state = run_query_with_state(monkeypatch, tmp_path, warnings_enabled=False)

    assert state['formatted'][0][1]['is_expanded'] is True


def test_run_query_uses_redirect_state_for_formatter(monkeypatch, tmp_path) -> None:
    state = run_query_with_state(monkeypatch, tmp_path, warnings_enabled=False)

    assert state['formatted'][0][1]['is_redirected'] is False


def test_run_query_does_not_style_regular_output_as_warnings(monkeypatch, tmp_path) -> None:
    state = run_query_with_state(monkeypatch, tmp_path, warnings_enabled=False)

    assert state['formatted'][0][1].get('is_warnings_style') is not True


def test_run_query_fetches_warnings_when_enabled(monkeypatch, tmp_path) -> None:
    state = run_query_with_state(monkeypatch, tmp_path)

    assert state['run_calls'] == ['select 1;\n', 'SHOW WARNINGS']


def test_run_query_styles_warning_output(monkeypatch, tmp_path) -> None:
    state = run_query_with_state(monkeypatch, tmp_path)

    assert state['formatted'][1][1]['is_warnings_style'] is True


def test_run_query_echoes_warning_output(monkeypatch, tmp_path) -> None:
    state = run_query_with_state(monkeypatch, tmp_path)

    assert state['echoed'][-1] == ('warnings', False)


def test_run_query_writes_checkpoint(monkeypatch, tmp_path) -> None:
    state = run_query_with_state(monkeypatch, tmp_path, warnings_enabled=False)

    assert state['checkpoint_path'].read_text(encoding='utf-8') == 'select 1;\n'


def test_get_last_query_returns_none() -> None:
    cli = make_bare_mycli()

    assert main.MyCli.get_last_query(cli) is None


def test_get_last_query_returns_latest_query() -> None:
    cli = make_bare_mycli()
    cli.query_history = [Query('select 1', True, False), Query('select 2', True, False)]

    assert main.MyCli.get_last_query(cli) == 'select 2'
