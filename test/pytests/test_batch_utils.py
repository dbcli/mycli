# type: ignore

from io import StringIO

import pytest

import mycli.packages.batch_utils
from mycli.packages.batch_utils import statements_from_filehandle


def collect_statements(sql: str) -> list[tuple[str, int]]:
    return list(statements_from_filehandle(StringIO(sql)))


def test_statements_from_filehandle_splits_on_statements() -> None:
    statements = collect_statements('select 1;\nselect\n 2;\nselect 3; select 4;\n')

    assert statements == [
        ('select 1;', 0),
        ('select\n 2;', 1),
        ('select 3;', 2),
        ('select 4;', 3),
    ]


def test_statements_from_filehandle_yields_trailing_statement_without_newline_01() -> None:
    statements = collect_statements('select 1;\nselect 2;')

    assert statements == [
        ('select 1;', 0),
        ('select 2;', 1),
    ]


def test_statements_from_filehandle_yields_trailing_statement_without_newline_02() -> None:
    statements = collect_statements('select 1;\nselect 2')

    assert statements == [
        ('select 1;', 0),
        ('select 2', 1),
    ]


def test_statements_from_filehandle_yields_trailing_statement_without_newline_03() -> None:
    statements = collect_statements('select 1\nwhere 1 == 1;')

    assert statements == [('select 1\nwhere 1 == 1;', 0)]


def test_statements_from_filehandle_rejects_overlong_statement(monkeypatch) -> None:
    monkeypatch.setattr(mycli.packages.batch_utils, 'MAX_MULTILINE_BATCH_STATEMENT', 2)

    with pytest.raises(ValueError, match='Saw single input statement greater than 2 lines'):
        list(statements_from_filehandle(StringIO('select 1,\n2\nwhere 1 = 1;')))


def test_statements_from_filehandle_yields_incorrect_sql() -> None:
    statements = collect_statements('select;\nselect 2')

    assert statements == [
        ('select;', 0),
        ('select 2', 1),
    ]


def test_statements_from_filehandle_yields_invalid_sql_01() -> None:
    statements = collect_statements('sellect;\nsellect 2')

    assert statements == [
        ('sellect;', 0),
        ('sellect 2', 1),
    ]


def test_statements_from_filehandle_yields_invalid_sql_02() -> None:
    statements = collect_statements('select `column;')

    assert statements == [
        ('select `column;', 0),
    ]


def test_statements_from_filehandle_continues_when_tokenizer_returns_no_tokens(monkeypatch) -> None:
    tokenize_calls: list[str] = []
    original_tokenize = mycli.packages.batch_utils.sqlglot.tokenize

    def fake_tokenize(sql: str, read: str):
        tokenize_calls.append(sql)
        if len(tokenize_calls) == 1:
            return []
        return original_tokenize(sql, read=read)

    monkeypatch.setattr(mycli.packages.batch_utils.sqlglot, 'tokenize', fake_tokenize)

    statements = list(statements_from_filehandle(StringIO('select 1;\nselect 2;')))

    assert tokenize_calls[0] == 'select 1;\n'
    assert statements == [
        ('select 1;', 0),
        ('select 2;', 1),
    ]
