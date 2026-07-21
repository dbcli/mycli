from __future__ import annotations

from typing import Any, Iterator

import pytest

import mycli.packages.polars_transform as polars_transform
from mycli.packages.polars_transform import (
    PolarsPipeline,
    PolarsTransform,
    PolarsTransformError,
    parse_polars_transform,
    prepare_polars_transform,
    run_polars_transform,
)
from mycli.packages.sqlresult import SQLResult
from mycli.types import OutputMode


class FakeDataFrame:
    written_paths: list[str] = []
    written_dataframes: list['FakeDataFrame'] = []

    def __init__(self, rows: list[tuple[Any, ...]], schema: list[str], orient: str) -> None:
        assert orient == 'row'
        self.rows = rows
        self.columns = schema
        self.parquet_paths: list[str] = []

    def iter_rows(self) -> Iterator[tuple[Any, ...]]:
        return iter(self.rows)

    def __len__(self) -> int:
        return len(self.rows)

    def write_parquet(self, path: str) -> None:
        self.parquet_paths.append(path)
        self.written_paths.append(path)
        self.written_dataframes.append(self)


class FakeSeries:
    def __init__(self, name: str, values: list[Any]) -> None:
        self.name = name
        self.values = values

    def __iter__(self) -> Iterator[Any]:
        return iter(self.values)

    def rename(self, name: str) -> 'FakeSeries':
        return FakeSeries(name, self.values)

    def to_frame(self) -> FakeDataFrame:
        return FakeDataFrame([(value,) for value in self.values], [self.name], 'row')


class FakePolars:
    DataFrame = FakeDataFrame
    Series = FakeSeries


class FailingDataFrame(FakeDataFrame):
    def write_parquet(self, path: str) -> None:
        raise OSError('disk full')


class FailingPolars:
    DataFrame = FailingDataFrame


class FakeAltair:
    pass


def make_transform(expression: str) -> PolarsTransform:
    return PolarsTransform(
        sql='SELECT id FROM orders',
        expression=expression,
        code=compile(expression, '<test>', 'eval'),
        polars=FakePolars,
        altair=FakeAltair,
    )


def test_parse_polars_transform_splits_sql_and_preserves_expression() -> None:
    assert parse_polars_transform("SELECT * FROM orders .| df.filter(pl.col('state') == 'open')") == PolarsPipeline(
        sql='SELECT * FROM orders',
        expression="df.filter(pl.col('state') == 'open')",
        parquet_path=None,
        output_mode='tabular',
    )


@pytest.mark.parametrize(
    ('command', 'output_mode'),
    [
        (r'SELECT * FROM orders \x .| df', 'explorer'),
        (r'SELECT * FROM orders .| df \x', 'explorer'),
        (r'SELECT * FROM orders .| df \G', 'expanded'),
    ],
)
def test_parse_polars_transform_returns_output_mode(command: str, output_mode: OutputMode) -> None:
    assert parse_polars_transform(command) == PolarsPipeline(
        sql='SELECT * FROM orders',
        expression='df',
        parquet_path=None,
        output_mode=output_mode,
    )


@pytest.mark.parametrize(
    ('command', 'expression', 'path'),
    [
        ('SELECT * FROM orders .> orders.parquet', None, 'orders.parquet'),
        ('SELECT * FROM orders .> orders.parquet;', None, 'orders.parquet'),
        ("SELECT * FROM orders .> 'order exports.parquet'", None, 'order exports.parquet'),
        ('SELECT * FROM orders .| df.head(10) .> orders.parquet', 'df.head(10)', 'orders.parquet'),
    ],
)
def test_parse_polars_transform_parses_parquet_redirect(
    command: str,
    expression: str | None,
    path: str,
) -> None:
    assert parse_polars_transform(command) == PolarsPipeline(
        sql='SELECT * FROM orders',
        expression=expression,
        parquet_path=path,
        output_mode='tabular',
    )


@pytest.mark.parametrize(
    'command',
    [
        "SELECT '.|' AS marker",
        'SELECT 1 /* .| df */',
        'SELECT 1.| df',
        'SELECT table.| df',
        'SELECT 1 .|df',
        'SELECT 1 .+ df',
    ],
)
def test_parse_polars_transform_ignores_non_suffix_markers(command: str) -> None:
    assert parse_polars_transform(command) is None


@pytest.mark.parametrize(
    ('command', 'message'),
    [
        (' .| df', 'require a SQL statement'),
        ('SELECT 1 .| ', 'require a Python expression'),
        ('SELECT 1 .|', 'require a Python expression'),
        ('SELECT 1; SELECT 2 .| df', 'exactly one SQL statement'),
        ('SELECT 1 .>', 'require a destination path'),
        ('SELECT 1 .> export.csv', 'end in ".parquet"'),
        ('SELECT 1 .> export file.parquet', 'must be quoted'),
        ('SELECT 1 .> export.parquet .| df', 'must follow'),
        ('SELECT 1 .| df .> export.parquet \\x', 'cannot use special display terminators'),
        ('SELECT 1 .| df .| df', 'only one ".|"'),
        ('SELECT 1 .> first.parquet .> second.parquet', 'only one ".>"'),
        ('SELECT 1 .> ;', 'require a destination path'),
    ],
)
def test_parse_polars_transform_rejects_invalid_commands(command: str, message: str) -> None:
    with pytest.raises(PolarsTransformError, match=message):
        parse_polars_transform(command)


def test_parse_polars_transform_reports_tokenizer_error(monkeypatch: pytest.MonkeyPatch) -> None:
    def fail_tokenize(command: str) -> list[Any]:
        raise polars_transform.sqlglot.errors.TokenError('bad token')

    monkeypatch.setattr(polars_transform.sqlglot, 'tokenize', fail_tokenize)

    with pytest.raises(PolarsTransformError, match='Unable to parse Polars transform'):
        parse_polars_transform('SELECT 1 .| df')


def test_parse_polars_transform_reports_sql_parser_error(monkeypatch: pytest.MonkeyPatch) -> None:
    def fail_parse(sql: str, *, read: str) -> list[Any]:
        raise polars_transform.sqlglot.errors.ParseError('bad SQL')

    monkeypatch.setattr(polars_transform.sqlglot, 'parse', fail_parse)

    with pytest.raises(PolarsTransformError, match='Unable to parse SQL before Polars transform'):
        parse_polars_transform('SELECT 1 .| df')


def test_parse_parquet_path_rejects_mismatched_quotes() -> None:
    with pytest.raises(PolarsTransformError, match='matching quotes'):
        polars_transform._parse_parquet_path("'orders.parquet")


def test_prepare_polars_transform_compiles_expression_and_loads_polars(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr('mycli.packages.polars_transform._load_polars', lambda: FakePolars)

    transform = prepare_polars_transform('SELECT id FROM orders', 'df')

    assert transform.sql == 'SELECT id FROM orders'
    assert transform.expression == 'df'
    assert transform.polars is FakePolars


def test_prepare_polars_transform_rejects_invalid_expression() -> None:
    with pytest.raises(PolarsTransformError, match='Invalid Polars transform expression'):
        prepare_polars_transform('SELECT 1', 'df[')


def test_prepare_polars_transform_reports_missing_dependency(monkeypatch: pytest.MonkeyPatch) -> None:
    def missing_polars() -> Any:
        raise PolarsTransformError('Polars transforms require Polars.')

    monkeypatch.setattr('mycli.packages.polars_transform._load_polars', missing_polars)

    with pytest.raises(PolarsTransformError, match='require Polars'):
        prepare_polars_transform('SELECT 1', 'df')


def test_load_polars_reports_missing_dependency(monkeypatch: pytest.MonkeyPatch) -> None:
    original_import = __import__

    def fail_polars_import(name: str, *args: Any, **kwargs: Any) -> Any:
        if name == 'polars':
            raise ImportError('not installed')
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr('builtins.__import__', fail_polars_import)

    with pytest.raises(PolarsTransformError, match='require Polars'):
        polars_transform._load_polars()


def test_load_polars_returns_imported_dependency(monkeypatch: pytest.MonkeyPatch) -> None:
    original_import = __import__

    def import_fake_polars(name: str, *args: Any, **kwargs: Any) -> Any:
        if name == 'polars':
            return FakePolars
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr('builtins.__import__', import_fake_polars)

    assert polars_transform._load_polars() is FakePolars


def test_load_altair_reports_missing_dependency(monkeypatch: pytest.MonkeyPatch) -> None:
    original_import = __import__

    def fail_altair_import(name: str, *args: Any, **kwargs: Any) -> Any:
        if name == 'altair':
            raise ImportError('not installed')
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr('builtins.__import__', fail_altair_import)

    with pytest.raises(PolarsTransformError, match='require Altair'):
        polars_transform._load_altair()


def test_run_polars_transform_materializes_and_renders_returned_dataframe() -> None:
    result = run_polars_transform(
        make_transform('df'),
        iter([SQLResult(header=['id'], rows=[(1,), (2,)])]),
    )

    assert result == SQLResult(header=['id'], rows=[(1,), (2,)])


@pytest.mark.parametrize(
    ('expression', 'header', 'rows'),
    [
        ("pl.Series('total', [1, None, 3])", ['total'], [(1,), (None,), (3,)]),
        ("pl.Series('', ['a', 'b'])", ['value'], [('a',), ('b',)]),
    ],
)
def test_run_polars_transform_renders_series(
    expression: str,
    header: list[str],
    rows: list[tuple[Any, ...]],
) -> None:
    result = run_polars_transform(
        make_transform(expression),
        iter([SQLResult(header=['id'], rows=[(1,)])]),
    )

    assert result == SQLResult(header=header, rows=rows)


def test_run_polars_transform_writes_raw_dataframe_to_parquet() -> None:
    transform = make_transform('df')
    FakeDataFrame.written_paths = []
    FakeDataFrame.written_dataframes = []

    result = run_polars_transform(
        transform,
        iter([SQLResult(header=['id'], rows=[(1,), (2,)])]),
        'orders.parquet',
    )

    assert result == SQLResult(status='Wrote 2 rows to orders.parquet.')
    assert FakeDataFrame.written_paths == ['orders.parquet']


@pytest.mark.parametrize(
    ('expression', 'column_name', 'rows'),
    [
        ("pl.Series('total', [1, None, 3])", 'total', [(1,), (None,), (3,)]),
        ("pl.Series('', ['a', 'b'])", 'value', [('a',), ('b',)]),
    ],
)
def test_run_polars_transform_writes_series_to_parquet(
    expression: str,
    column_name: str,
    rows: list[tuple[Any, ...]],
) -> None:
    FakeDataFrame.written_paths = []
    FakeDataFrame.written_dataframes = []

    result = run_polars_transform(
        make_transform(expression),
        iter([SQLResult(header=['id'], rows=[(1,)])]),
        'series.parquet',
    )

    assert result == SQLResult(status=f'Wrote {len(rows)} rows to series.parquet.')
    assert FakeDataFrame.written_paths == ['series.parquet']
    assert FakeDataFrame.written_dataframes[-1].columns == [column_name]
    assert FakeDataFrame.written_dataframes[-1].rows == rows


def test_run_polars_transform_reports_series_parquet_write_error(monkeypatch: pytest.MonkeyPatch) -> None:
    def fail_write(self: FakeDataFrame, path: str) -> None:
        raise OSError('disk full')

    monkeypatch.setattr(FakeDataFrame, 'write_parquet', fail_write)

    with pytest.raises(PolarsTransformError, match='Unable to write Parquet file'):
        run_polars_transform(
            make_transform("pl.Series('total', [1])"),
            iter([SQLResult(header=['id'], rows=[(1,)])]),
            'series.parquet',
        )


def test_run_polars_transform_reports_parquet_write_error() -> None:
    transform = PolarsTransform(
        sql='SELECT id FROM orders',
        expression='df',
        code=compile('df', '<test>', 'eval'),
        polars=FailingPolars,
        altair=FakeAltair,
    )

    with pytest.raises(PolarsTransformError, match='Unable to write Parquet file'):
        run_polars_transform(
            transform,
            iter([SQLResult(header=['id'], rows=[(1,)])]),
            'orders.parquet',
        )


def test_run_polars_transform_rejects_non_tabular_parquet_output() -> None:
    with pytest.raises(PolarsTransformError, match='must return a DataFrame or Series'):
        run_polars_transform(
            make_transform('1'),
            iter([SQLResult(header=['id'], rows=[(1,)])]),
            'orders.parquet',
        )


def test_run_polars_transform_reports_non_dataframe_result() -> None:
    result = run_polars_transform(
        make_transform('1'),
        iter([SQLResult(header=['id'], rows=[(1,)])]),
    )

    assert result.status_plain == "Nothing could be displayed for return type: <class 'int'>"


def test_prepare_polars_transform_supports_direct_parquet_output(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr('mycli.packages.polars_transform._load_polars', lambda: FakePolars)

    transform = prepare_polars_transform('SELECT id FROM orders', None)

    assert transform.expression is None
    assert transform.altair is None


@pytest.mark.parametrize(
    'results',
    [
        iter([]),
        iter([SQLResult(status='OK')]),
        iter([SQLResult(header=['id'], rows=[(1,)]), SQLResult(status='OK')]),
    ],
)
def test_run_polars_transform_rejects_non_single_tabular_result(results: Iterator[SQLResult]) -> None:
    with pytest.raises(PolarsTransformError):
        run_polars_transform(make_transform('df'), results)


def test_run_polars_transform_reports_expression_error() -> None:
    with pytest.raises(PolarsTransformError, match='ZeroDivisionError'):
        run_polars_transform(make_transform('1 / 0'), iter([SQLResult(header=['id'], rows=[(1,)])]))
