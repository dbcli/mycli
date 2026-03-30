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
