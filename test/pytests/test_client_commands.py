from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import pytest

from mycli import client_commands
from mycli.client_commands import ClientCommandsMixin
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

    assert [call[1] for call in calls] == ['use', 'connect', 'rehash', 'tableformat', 'redirectformat', 'source', 'prompt']
    assert calls[0][0] == client.change_db
    assert calls[1][0] == client.manual_reconnect
    assert calls[2][0] == client.refresh_completions
    assert calls[3][0] == client.change_table_format
    assert calls[4][0] == client.change_redirect_format
    assert calls[5][0] == client.execute_from_file
    assert calls[6][0] == client.change_prompt_format


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


def test_execute_from_file_stops_when_destructive_query_is_rejected(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    client = DummyClient()
    sql_file = tmp_path / 'query.sql'
    sql_file.write_text('drop table users;', encoding='utf-8')
    client.destructive_warning = True
    client.destructive_keywords = {'drop'}
    monkeypatch.setattr(client_commands, 'confirm_destructive_query', lambda keywords, query: False)

    assert list(client.execute_from_file(str(sql_file))) == [SQLResult(status='Wise choice. Command execution stopped.')]


def test_execute_from_file_runs_file_query(tmp_path: Path) -> None:
    client = DummyClient()
    sql_file = tmp_path / 'query.sql'
    sql_file.write_text('select 1;', encoding='utf-8')
    client.destructive_warning = False
    client.destructive_keywords = set()
    client.sqlexecute = FakeSQLExecute()

    assert list(client.execute_from_file(str(sql_file))) == [SQLResult(status='ran select 1;')]
    assert client.sqlexecute.runs == ['select 1;']


def test_change_prompt_format_requires_argument() -> None:
    client = DummyClient()

    assert client.change_prompt_format('') == [SQLResult(status='Missing required argument, format.')]


def test_change_prompt_format_updates_prompt_format() -> None:
    client = DummyClient()

    assert client.change_prompt_format('\\u> ') == [SQLResult(status='Changed prompt format to \\u> ')]
    assert client.prompt_format == '\\u> '


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
