from __future__ import annotations

from collections.abc import Generator
from io import StringIO
import logging
from pathlib import Path
from typing import Any

from configobj import ConfigObj
import pytest

from mycli import client_commands
from mycli.client_commands import ClientCommandsMixin
from mycli.packages import special
from mycli.packages.special import main as special_main
from mycli.packages.sqlresult import SQLResult


class DummyClient(ClientCommandsMixin):
    def __init__(self) -> None:
        self.echo_calls: list[tuple[tuple[Any, ...], dict[str, Any]]] = []

    def echo(self, *args: Any, **kwargs: Any) -> None:
        self.echo_calls.append((args, kwargs))

    def reconnect(self, database: str = '') -> bool:
        self.reconnect_database = database
        return True

    def refresh_completions(self, reset: bool = False) -> list[SQLResult]:
        return [SQLResult(status=f'refresh {reset}')]


class FakeFormatter:
    def __init__(self, *, supported_formats: list[str] | None = None, fail: bool = False) -> None:
        self.supported_formats = supported_formats or ['ascii', 'csv']
        self.fail = fail
        self.values: list[str] = []

    @property
    def format_name(self) -> str:
        return self.values[-1]

    @format_name.setter
    def format_name(self, value: str) -> None:
        if self.fail:
            raise ValueError
        self.values.append(value)


class FakeSQLExecute:
    def __init__(self, *, dbname: str = 'old_db', user: str = 'alice') -> None:
        self.dbname = dbname
        self.user = user
        self.changed_to: list[str] = []
        self.runs: list[str] = []

    def change_db(self, dbname: str) -> None:
        self.changed_to.append(dbname)
        self.dbname = dbname

    def run(self, query: str) -> list[SQLResult]:
        self.runs.append(query)
        return [SQLResult(status=f'ran {query}')]


class IteratedFile(StringIO):
    def read(self, *args: Any, **kwargs: Any) -> str:
        raise AssertionError('Source files must not be read in full.')


class FailingFile:
    def __init__(self) -> None:
        self.closed = False

    def __enter__(self) -> FailingFile:
        return self

    def __exit__(self, *args: Any) -> None:
        self.closed = True

    def __iter__(self) -> FailingFile:
        return self

    def __next__(self) -> str:
        raise OSError('read failed')


@pytest.fixture(autouse=True)
def patch_sql_execute(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(client_commands, 'SQLExecute', FakeSQLExecute)


def result_statuses(results: Any) -> list[str | None]:
    return [result.status for result in list(results)]


def test_register_special_commands_registers_expected_commands(monkeypatch: pytest.MonkeyPatch) -> None:
    client = DummyClient()
    calls: list[tuple[Any, ...]] = []
    monkeypatch.setattr(client_commands.special, 'register_special_command', lambda *args, **kwargs: calls.append((*args, kwargs)))

    client.register_special_commands()

    assert [call[1] for call in calls] == [
        'use',
        'connect',
        'rehash',
        'tableformat',
        'redirectformat',
        'source',
        'prompt',
        r'\config',
    ]
    assert calls[0][0] == client.change_db
    assert calls[1][0] == client.manual_reconnect
    assert calls[2][0] == client.refresh_completions
    assert calls[3][0] == client.change_table_format
    assert calls[4][0] == client.change_redirect_format
    assert calls[5][0] == client.execute_from_file
    assert calls[6][0] == client.change_prompt_format
    assert calls[6][2:4] == ('/prompt [string]', 'Show or change prompt format.')
    assert calls[7][0] == client.config_command
    assert calls[7][2:4] == ('/config <help|get|search|edit> [key]', 'Inspect settings from config files.')


def test_manual_reconnect_reports_not_connected() -> None:
    client = DummyClient()

    def fake_reconnect(database: str = '') -> bool:
        client.reconnect_database = database
        return False

    client.reconnect = fake_reconnect  # type: ignore[method-assign]

    assert result_statuses(client.manual_reconnect('new_db')) == ['Not connected']
    assert client.reconnect_database == 'new_db'


def test_manual_reconnect_without_database_returns_empty_result() -> None:
    client = DummyClient()

    assert list(client.manual_reconnect()) == [SQLResult()]
    assert client.reconnect_database == ''


def test_manual_reconnect_with_database_delegates_to_change_db(monkeypatch: pytest.MonkeyPatch) -> None:
    client = DummyClient()
    changed: list[str] = []

    def fake_change_db(arg: str, **_: Any) -> Any:
        changed.append(arg)
        yield SQLResult(status='changed')

    monkeypatch.setattr(client, 'change_db', fake_change_db)

    assert result_statuses(client.manual_reconnect('new_db')) == ['changed']
    assert changed == ['new_db']


def test_change_table_format_reports_supported_formats_on_error() -> None:
    client = DummyClient()
    client.main_formatter = FakeFormatter(supported_formats=['plain', 'csv'], fail=True)

    assert result_statuses(client.change_table_format('bad')) == ['Table format bad not recognized. Allowed formats:\n\tplain\n\tcsv']


def test_change_table_format_updates_formatter() -> None:
    client = DummyClient()
    client.main_formatter = FakeFormatter()

    assert result_statuses(client.change_table_format('csv')) == ['Changed table format to csv']
    assert client.main_formatter.values == ['csv']


def test_change_redirect_format_updates_formatter() -> None:
    client = DummyClient()
    client.redirect_formatter = FakeFormatter()

    assert result_statuses(client.change_redirect_format('csv')) == ['Changed redirect format to csv']
    assert client.redirect_formatter.values == ['csv']


def test_change_redirect_format_reports_supported_formats_on_error() -> None:
    client = DummyClient()
    client.redirect_formatter = FakeFormatter(supported_formats=['plain', 'json'], fail=True)

    assert result_statuses(client.change_redirect_format('bad')) == [
        'Redirect format bad not recognized. Allowed formats:\n\tplain\n\tjson'
    ]


def test_config_command_returns_unquoted_configobj_value(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(special_main, 'COMMANDS', {})
    monkeypatch.setattr(special_main, 'CASE_SENSITIVE_COMMANDS', set())
    monkeypatch.setattr(special_main, 'CASE_INSENSITIVE_COMMANDS', set())
    client = DummyClient()
    client.config = ConfigObj(
        StringIO('[main]\nshow_warnings = "False"\n'),
        interpolation=False,
    )
    client.register_special_commands()

    config_result = [SQLResult(header=['Key', 'Value'], rows=[('main.show_warnings', 'False')])]
    assert special.execute(None, '/config get main.show_warnings') == config_result
    assert special.execute(None, r'\config get main.show_warnings') == config_result
    assert special.execute(None, '/config search SHOW_WARNINGS') == config_result
    assert special.execute(None, r'\config search SHOW_WARNINGS') == config_result
    with pytest.raises(special.CommandNotFound, match='Command not found: select'):
        special.execute(None, r'select 1 \config get main.show_warnings')


def test_config_edit_opens_user_config_for_slash_and_backslash_commands(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(special_main, 'COMMANDS', {})
    monkeypatch.setattr(special_main, 'CASE_SENSITIVE_COMMANDS', set())
    monkeypatch.setattr(special_main, 'CASE_INSENSITIVE_COMMANDS', set())
    client = DummyClient()
    client.myclirc_path = str(tmp_path / 'myclirc')
    write_calls: list[tuple[str, bool]] = []
    edit_calls: list[str] = []
    monkeypatch.setattr(
        client_commands,
        'write_default_config',
        lambda path, overwrite: write_calls.append((path, overwrite)),
    )
    monkeypatch.setattr(client_commands.click, 'edit', lambda *, filename: edit_calls.append(filename))
    client.register_special_commands()

    result = [SQLResult(status=f'Config file edited: {client.myclirc_path}. Restart mycli to apply changes.')]
    assert special.execute(None, '/config edit') == result
    assert special.execute(None, r'\config edit') == result
    assert write_calls == [(client.myclirc_path, False), (client.myclirc_path, False)]
    assert edit_calls == [client.myclirc_path, client.myclirc_path]


@pytest.mark.parametrize(
    ('failure_source', 'error'),
    (
        ('write', OSError('permission denied')),
        ('edit', client_commands.click.ClickException('editor failed')),
    ),
)
def test_config_edit_reports_file_and_editor_errors(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    failure_source: str,
    error: Exception,
) -> None:
    client = DummyClient()
    client.myclirc_path = str(tmp_path / 'myclirc')

    def write_default_config(path: str, overwrite: bool) -> None:
        if failure_source == 'write':
            raise error

    def edit(*, filename: str) -> None:
        if failure_source == 'edit':
            raise error

    monkeypatch.setattr(client_commands, 'write_default_config', write_default_config)
    monkeypatch.setattr(client_commands.click, 'edit', edit)

    assert client.config_command('edit') == [SQLResult(status=f'Unable to edit config file "{client.myclirc_path}": {error}')]


def test_config_edit_handles_keyboard_interrupt(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    client = DummyClient()
    client.myclirc_path = str(tmp_path / 'myclirc')
    monkeypatch.setattr(client_commands, 'write_default_config', lambda path, overwrite: None)

    def edit(*, filename: str) -> None:
        raise KeyboardInterrupt

    monkeypatch.setattr(client_commands.click, 'edit', edit)

    assert client.config_command('edit') == [SQLResult(status='Config edit cancelled.')]


def test_config_command_resolves_dotted_keys_and_renders_lists() -> None:
    client = DummyClient()
    client.config = {
        'colors': {'sql.keyword': 'bold blue'},
        'alias_dsn.init-commands': {'prod': ['set one=1', 'set two=2']},
        'alias_dsn_extra': {'prod': 'visible'},
        'nested': {'inner': {'value': 42}},
    }

    assert client.config_command('get colors.sql.keyword') == [
        SQLResult(header=['Key', 'Value'], rows=[('colors.sql.keyword', 'bold blue')])
    ]
    assert client.config_command('get alias_dsn.init-commands.prod') == [
        SQLResult(header=['Key', 'Value'], rows=[('alias_dsn.init-commands.prod', 'set one=1, set two=2')])
    ]
    assert client.config_command('get alias_dsn_extra.prod') == [
        SQLResult(header=['Key', 'Value'], rows=[('alias_dsn_extra.prod', 'visible')])
    ]
    assert client.config_command('GET nested.inner.value') == [SQLResult(header=['Key', 'Value'], rows=[('nested.inner.value', '42')])]


def test_get_config_property_names_returns_visible_leaf_paths() -> None:
    config = {
        'main': {'show_warnings': 'False', 'empty_section': {}},
        'alias_dsn': {'prod': 'mysql://user:password@host/database'},
        'favorite_queries': {'report': 'select secret from reports'},
        'alias_dsn.init-commands': {'prod': ['set one=1', 'set two=2']},
    }

    assert client_commands.get_config_property_names(config) == [
        'alias_dsn.init-commands.prod',
        'main.show_warnings',
    ]


def test_config_command_searches_paths_and_rendered_values_case_insensitively() -> None:
    client = DummyClient()
    client.config = {
        'main': {'show_warnings': 'False', 'empty': ''},
        'colors': {'sql.keyword': 'bold BLUE'},
        'lists': {'commands': ['set one=1', 'set two=2']},
    }

    assert client.config_command(r'search SHOW_WARNINGS|bold blue|set one\s*=') == [
        SQLResult(
            header=['Key', 'Value'],
            rows=[
                ('colors.sql.keyword', 'bold BLUE'),
                ('lists.commands', 'set one=1, set two=2'),
                ('main.show_warnings', 'False'),
            ],
        )
    ]
    assert client.config_command('search ^$') == [SQLResult(header=['Key', 'Value'], rows=[('main.empty', '')])]


def test_config_command_search_excludes_hidden_sections() -> None:
    client = DummyClient()
    client.config = {
        'alias_dsn': {'prod': 'mysql://user:password@host/database'},
        'favorite_queries': {'report': 'select secret from reports'},
        'alias_dsn.init-commands': {'prod': 'set visible=1'},
        'alias_dsn_extra': {'prod': 'also visible'},
    }

    assert client.config_command('search password|secret|report') == [
        SQLResult(status='No configuration values match "password|secret|report".')
    ]
    assert client.config_command('search visible') == [
        SQLResult(
            header=['Key', 'Value'],
            rows=[
                ('alias_dsn.init-commands.prod', 'set visible=1'),
                ('alias_dsn_extra.prod', 'also visible'),
            ],
        )
    ]


@pytest.mark.parametrize(
    ('arg', 'status'),
    (
        ('search does-not-match', 'No configuration values match "does-not-match".'),
        ('search [', 'Invalid regular expression: unterminated character set at position 0.'),
    ),
)
def test_config_command_search_reports_errors(arg: str, status: str) -> None:
    client = DummyClient()
    client.config = {'main': {'show_warnings': 'False'}}

    assert client.config_command(arg) == [SQLResult(status=status)]


@pytest.mark.parametrize(
    'path',
    (
        'alias_dsn',
        'alias_dsn.prod',
        'alias_dsn.missing',
    ),
)
def test_config_command_hides_dsn_aliases(path: str) -> None:
    client = DummyClient()
    client.config = {
        'alias_dsn': {'prod': 'mysql://user:password@host/database'},
        'favorite_queries': {'report': 'select secret from reports'},
    }

    assert client.config_command(f'get {path}') == [SQLResult(status='See "/dsn list" for DSNs.')]


@pytest.mark.parametrize(
    'path',
    (
        'favorite_queries',
        'favorite_queries.report',
        'favorite_queries.missing',
    ),
)
def test_config_command_hides_favorite_queries(path: str) -> None:
    client = DummyClient()
    client.config = {
        'alias_dsn': {'prod': 'mysql://user:password@host/database'},
        'favorite_queries': {'report': 'select secret from reports'},
    }

    assert client.config_command(f'get {path}') == [SQLResult(status='See "/f" for favorite queries.')]


@pytest.mark.parametrize(
    ('arg', 'preamble'),
    (
        ('', client_commands.CONFIG_COMMAND_USAGE),
        ('help', client_commands.CONFIG_COMMAND_USAGE),
        ('get', client_commands.CONFIG_COMMAND_USAGE),
        ('search', client_commands.CONFIG_COMMAND_USAGE),
        ('edit extra', client_commands.CONFIG_COMMAND_USAGE),
        ('list main.show_warnings', client_commands.CONFIG_COMMAND_USAGE),
        ('get main.show_warnings extra', client_commands.CONFIG_COMMAND_USAGE),
    ),
)
def test_config_command_returns_usage(arg: str, preamble: str) -> None:
    client = DummyClient()
    client.config = {'main': {'show_warnings': 'False', 'empty': ''}}

    assert client.config_command(arg) == [SQLResult(preamble=preamble)]


@pytest.mark.parametrize(
    ('arg', 'status'),
    (
        ('get main.missing', 'Config key not found: main.missing.'),
        ('get main.show_warnings.extra', 'Config key not found: main.show_warnings.extra.'),
        ('get main', 'Config path is not a value: main.'),
    ),
)
def test_config_command_reports_errors(arg: str, status: str) -> None:
    client = DummyClient()
    client.config = {'main': {'show_warnings': 'False', 'empty': ''}}

    assert client.config_command(arg) == [SQLResult(status=status)]


def test_config_command_reports_empty_values() -> None:
    client = DummyClient()
    client.config = {'main': {'show_warnings': 'False', 'empty': ''}}

    assert client.config_command('get main.empty') == [SQLResult(header=['Key', 'Value'], rows=[('main.empty', '')])]


def test_change_db_unquotes_mysql_identifier(monkeypatch: pytest.MonkeyPatch) -> None:
    client = DummyClient()
    client.sqlexecute = FakeSQLExecute()
    title_calls: list[DummyClient] = []
    monkeypatch.setattr(client_commands, 'set_all_external_titles', lambda value: title_calls.append(value))

    assert result_statuses(client.change_db('`new``db`')) == ['You are now connected to database "new`db" as user "alice"']
    assert client.sqlexecute.changed_to == ['new`db']
    assert title_calls == [client]


def test_change_db_reports_when_database_is_already_selected(monkeypatch: pytest.MonkeyPatch) -> None:
    client = DummyClient()
    client.sqlexecute = FakeSQLExecute(dbname='same_db')
    title_calls: list[DummyClient] = []
    monkeypatch.setattr(client_commands, 'set_all_external_titles', lambda value: title_calls.append(value))

    assert result_statuses(client.change_db('same_db')) == ['You are already connected to database "same_db" as user "alice"']
    assert client.sqlexecute.changed_to == []
    assert title_calls == [client]


def test_change_db_without_argument_reports_error(monkeypatch: pytest.MonkeyPatch) -> None:
    client = DummyClient()
    secho_calls: list[tuple[str, dict[str, Any]]] = []
    monkeypatch.setattr(client_commands.click, 'secho', lambda message, **kwargs: secho_calls.append((message, kwargs)))

    assert list(client.change_db('')) == []
    assert secho_calls == [('No database selected', {'err': True, 'fg': 'red'})]


def test_execute_from_file_requires_filename() -> None:
    client = DummyClient()

    assert list(client.execute_from_file('')) == [SQLResult(status='Missing required argument: filename.')]


def test_execute_from_file_reports_open_errors() -> None:
    client = DummyClient()

    result = list(client.execute_from_file('/does/not/exist.sql'))

    assert len(result) == 1
    assert result[0].status is not None
    assert '/does/not/exist.sql' in result[0].status


def test_execute_from_file_skips_rejected_destructive_query(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    client = DummyClient()
    sql_file = tmp_path / 'query.sql'
    sql_file.write_text('drop table users;\nselect 1;', encoding='utf-8')
    client.destructive_warning = True
    client.destructive_keywords = {'drop'}
    client.sqlexecute = FakeSQLExecute()
    confirmation_queries: list[str] = []

    def confirm_destructive_query(keywords: set[str], query: str) -> bool:
        confirmation_queries.append(query)
        return not query.startswith('drop')

    monkeypatch.setattr(client_commands, 'confirm_destructive_query', confirm_destructive_query)

    assert list(client.execute_from_file(str(sql_file))) == [SQLResult(status='ran select 1;')]
    assert client.sqlexecute.runs == ['select 1;']
    assert confirmation_queries == ['drop table users;', 'select 1;']


def test_execute_from_file_runs_accepted_destructive_query(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    client = DummyClient()
    sql_file = tmp_path / 'query.sql'
    sql_file.write_text('drop table users;', encoding='utf-8')
    client.destructive_warning = True
    client.destructive_keywords = {'drop'}
    client.sqlexecute = FakeSQLExecute()
    monkeypatch.setattr(client_commands, 'confirm_destructive_query', lambda keywords, query: True)

    assert list(client.execute_from_file(str(sql_file))) == [SQLResult(status='ran drop table users;')]
    assert client.sqlexecute.runs == ['drop table users;']


def test_execute_from_file_iterates_statements_without_reading_entire_file(monkeypatch: pytest.MonkeyPatch) -> None:
    client = DummyClient()
    client.destructive_warning = False
    client.destructive_keywords = set()
    client.sqlexecute = FakeSQLExecute()
    file_h = IteratedFile('select 1;\nselect\n 2;\nselect 3; select 4;\nselect 5')
    opened_paths: list[str] = []

    def open_file(path: str) -> IteratedFile:
        opened_paths.append(path)
        return file_h

    monkeypatch.setattr(client_commands.os.path, 'expanduser', lambda path: '/expanded/query.sql')
    monkeypatch.setattr(client_commands, 'open', open_file, raising=False)

    assert result_statuses(client.execute_from_file('~/query.sql')) == [
        'ran select 1;',
        'ran select\n 2;',
        'ran select 3;',
        'ran select 4;',
        'ran select 5',
    ]
    assert opened_paths == ['/expanded/query.sql']
    assert file_h.closed is True


def test_execute_from_file_reports_read_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    client = DummyClient()
    client.sqlexecute = FakeSQLExecute()
    file_h = FailingFile()
    monkeypatch.setattr(client_commands, 'open', lambda path: file_h, raising=False)

    assert list(client.execute_from_file('query.sql')) == [SQLResult(status='read failed')]
    assert file_h.closed is True


def test_execute_from_file_reports_parser_errors(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    client = DummyClient()
    client.sqlexecute = FakeSQLExecute()
    sql_file = tmp_path / 'query.sql'
    sql_file.write_text('select 1;', encoding='utf-8')

    def invalid_statements(file_h: StringIO) -> Generator[tuple[str, int], None, None]:
        yield from ()
        raise ValueError('invalid batch input')

    monkeypatch.setattr(client_commands, 'statements_from_filehandle', invalid_statements)

    assert list(client.execute_from_file(str(sql_file))) == [SQLResult(status='invalid batch input')]


def test_execute_from_file_does_not_report_query_errors_as_file_errors(tmp_path: Path) -> None:
    client = DummyClient()
    client.destructive_warning = False
    client.sqlexecute = FakeSQLExecute()
    client.sqlexecute.run = lambda query: (_ for _ in ()).throw(OSError('query failed'))  # type: ignore[method-assign]
    sql_file = tmp_path / 'query.sql'
    sql_file.write_text('select 1;', encoding='utf-8')

    with pytest.raises(OSError, match='query failed'):
        list(client.execute_from_file(str(sql_file)))


def test_execute_from_empty_file_returns_no_results(tmp_path: Path) -> None:
    client = DummyClient()
    client.sqlexecute = FakeSQLExecute()
    sql_file = tmp_path / 'query.sql'
    sql_file.write_text('', encoding='utf-8')

    assert list(client.execute_from_file(str(sql_file))) == []


def test_execute_from_file_runs_file_query(tmp_path: Path) -> None:
    client = DummyClient()
    sql_file = tmp_path / 'query.sql'
    sql_file.write_text('select 1;', encoding='utf-8')
    client.destructive_warning = False
    client.destructive_keywords = set()
    client.sqlexecute = FakeSQLExecute()

    assert list(client.execute_from_file(str(sql_file))) == [SQLResult(status='ran select 1;')]
    assert client.sqlexecute.runs == ['select 1;']


@pytest.mark.parametrize('command', ['/fs report select 1; select 2;', '\\fs report select 1; select 2;', 'pager;'])
def test_execute_from_file_rejects_special_commands(command: str, tmp_path: Path) -> None:
    client = DummyClient()
    sql_file = tmp_path / 'query.sql'
    sql_file.write_text(command, encoding='utf-8')
    client.destructive_warning = False
    client.destructive_keywords = set()
    client.sqlexecute = FakeSQLExecute()

    assert list(client.execute_from_file(str(sql_file))) == [SQLResult(status='Special commands are not supported in source files.')]
    assert client.sqlexecute.runs == []


def test_execute_from_file_allows_sql_comments(tmp_path: Path) -> None:
    client = DummyClient()
    sql_file = tmp_path / 'query.sql'
    sql_file.write_text('/* comment */ select 1;', encoding='utf-8')
    client.destructive_warning = False
    client.destructive_keywords = set()
    client.sqlexecute = FakeSQLExecute()

    assert list(client.execute_from_file(str(sql_file))) == [SQLResult(status='ran /* comment */ select 1;')]
    assert client.sqlexecute.runs == ['/* comment */ select 1;']


def test_change_prompt_format_without_argument_shows_current_format() -> None:
    client = DummyClient()
    client.prompt_format = '\\u> '

    assert client.change_prompt_format('') == [SQLResult(status='Prompt format: "\\u> "')]
    assert client.prompt_format == '\\u> '


def test_change_prompt_format_updates_prompt_format() -> None:
    client = DummyClient()

    assert client.change_prompt_format('\\u> ') == [SQLResult(status='Changed prompt format to: "\\u> "')]
    assert client.prompt_format == '\\u> '


@pytest.mark.parametrize(
    ('command', 'quote'),
    [
        ('/prompt', '"'),
        (r'\R', "'"),
    ],
)
def test_change_prompt_format_accepts_quoted_value(
    monkeypatch: pytest.MonkeyPatch,
    command: str,
    quote: str,
) -> None:
    monkeypatch.setattr(special_main, 'COMMANDS', {})
    monkeypatch.setattr(special_main, 'CASE_SENSITIVE_COMMANDS', set())
    monkeypatch.setattr(special_main, 'CASE_INSENSITIVE_COMMANDS', set())
    client = DummyClient()
    client.prompt_format = 'old> '
    client.register_special_commands()

    result = special.execute(None, f'{command} {quote} \\u> {quote}')

    assert result == [SQLResult(status='Changed prompt format to: " \\u> "')]
    assert client.prompt_format == ' \\u> '


@pytest.mark.parametrize('arg', ["''", '""'])
def test_change_prompt_format_accepts_quoted_empty_value(arg: str) -> None:
    client = DummyClient()
    client.prompt_format = 'old> '

    result = client.change_prompt_format(arg)

    assert result == [SQLResult(status='Changed prompt format to: ""')]
    assert client.prompt_format == ''


@pytest.mark.parametrize('arg', ["'unmatched", '"unmatched'])
def test_change_prompt_format_keeps_unmatched_quote(arg: str) -> None:
    client = DummyClient()

    client.change_prompt_format(arg)

    assert client.prompt_format == arg


def test_initialize_logging_uses_null_handler_for_none_level(monkeypatch: pytest.MonkeyPatch) -> None:
    client = DummyClient()
    client.config = {'main': {'log_file': '/unused/mycli.log', 'log_level': 'NONE'}}
    capture_warning_calls: list[bool] = []
    monkeypatch.setattr(client_commands.logging, 'captureWarnings', lambda value: capture_warning_calls.append(value))
    logger = logging.getLogger('mycli')
    original_handlers = list(logger.handlers)
    try:
        client.initialize_logging()

        added_handlers = [handler for handler in logger.handlers if handler not in original_handlers]
        assert len(added_handlers) == 1
        assert isinstance(added_handlers[0], logging.NullHandler)
        assert logger.level == logging.CRITICAL
        assert capture_warning_calls == [True]
    finally:
        for handler in logger.handlers:
            if handler not in original_handlers:
                logger.removeHandler(handler)


def test_initialize_logging_uses_file_handler(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    log_file = tmp_path / 'mycli.log'
    client = DummyClient()
    client.config = {'main': {'log_file': str(log_file), 'log_level': 'DEBUG'}}
    capture_warning_calls: list[bool] = []
    monkeypatch.setattr(client_commands.logging, 'captureWarnings', lambda value: capture_warning_calls.append(value))
    logger = logging.getLogger('mycli')
    original_handlers = list(logger.handlers)
    try:
        client.initialize_logging()

        added_handlers = [handler for handler in logger.handlers if handler not in original_handlers]
        assert len(added_handlers) == 1
        assert isinstance(added_handlers[0], logging.FileHandler)
        assert logger.level == logging.DEBUG
        assert capture_warning_calls == [True]
    finally:
        for handler in logger.handlers:
            if handler not in original_handlers:
                logger.removeHandler(handler)
                handler.close()


def test_initialize_logging_reports_invalid_log_path() -> None:
    client = DummyClient()
    client.config = {'main': {'log_file': '/does/not/exist/mycli.log', 'log_level': 'INFO'}}

    client.initialize_logging()

    assert client.echo_calls == [(('Error: Unable to open the log file "/does/not/exist/mycli.log".',), {'err': True, 'fg': 'red'})]
