from typing import Any, cast
from unittest.mock import Mock, call

from pymysql.connections import Connection
import pytest

from mycli.packages.tabular_output import sql_format


@pytest.fixture
def formatter(monkeypatch: pytest.MonkeyPatch) -> Mock:
    connection = Connection(defer_connect=True)
    connection.server_status = 0
    formatter = Mock(query='select * from records')
    formatter.mycli.sql_execute.conn = connection
    monkeypatch.setattr(sql_format, 'formatter', formatter, raising=False)
    return formatter


@pytest.mark.parametrize(
    ('value', 'expected'),
    [(b'\x00\xab\xff', '0x00abff'), (b'', '0x'), ("it's", "'it\\'s'"), (None, 'NULL'), (42, '42')],
)
def test_escape_sql_value(formatter: Mock, value: object, expected: str) -> None:
    assert sql_format.escape_for_sql_statement(cast(Any, value)) == expected


@pytest.mark.parametrize(
    ('query', 'table'),
    [
        ('select 1', '`DUAL`'),
        ('select * from `records`', 'records'),
        ('select * from `app`.`records`', 'app.records'),
        ('select * from records join others on records.id = others.id', 'records'),
    ],
)
def test_insert_uses_first_query_table(formatter: Mock, query: str, table: str) -> None:
    formatter.query = query

    assert list(sql_format.adapter(cast(Any, [[1]]), ['id'], table_format='sql-insert')) == [
        f'INSERT INTO {table} (`id`) VALUES',
        '  (1)',
        ';',
    ]


def test_insert_separates_multiple_rows(formatter: Mock) -> None:
    rows = [[1, 'first', b'\xab'], [2, None, b'\xcd']]

    assert list(sql_format.adapter(cast(Any, rows), ['id', 'name', 'data'], table_format='sql-insert')) == [
        'INSERT INTO records (`id`, `name`, `data`) VALUES',
        "  (1, 'first', 0xab)",
        ', (2, NULL, 0xcd)',
        ';',
    ]


@pytest.mark.parametrize('table_format', ['sql-update', 'sql-update-1'])
def test_update_uses_first_column_as_key(formatter: Mock, table_format: str) -> None:
    rows = [[1, 'first', None], [2, 'second', 'value']]

    assert list(sql_format.adapter(cast(Any, rows), ['id', 'name', 'optional'], table_format=table_format)) == [
        'UPDATE records SET',
        "  `name` = 'first'",
        ', `optional` = NULL',
        'WHERE `id` = 1;',
        'UPDATE records SET',
        "  `name` = 'second'",
        ", `optional` = 'value'",
        'WHERE `id` = 2;',
    ]


def test_update_uses_composite_key(formatter: Mock) -> None:
    rows = [[1, 'group', 'value']]

    assert list(sql_format.adapter(cast(Any, rows), ['id', 'group', 'name'], table_format='sql-update-2')) == [
        'UPDATE records SET',
        "  `name` = 'value'",
        "WHERE `id` = 1 AND `group` = 'group';",
    ]


@pytest.mark.parametrize('table_format', [None, 'unrecognized'])
def test_unsupported_format_emits_nothing(formatter: Mock, table_format: str | None) -> None:
    assert list(sql_format.adapter(cast(Any, [[1]]), ['id'], table_format=table_format)) == []


def test_registers_all_sql_formats(formatter: Mock) -> None:
    replacement = Mock()

    sql_format.register_new_formatter(replacement)

    assert sql_format.formatter is replacement
    assert replacement.register_new_formatter.call_args_list == [
        call(name, sql_format.adapter, (), {'table_format': name}) for name in ('sql-insert', 'sql-update', 'sql-update-1', 'sql-update-2')
    ]
