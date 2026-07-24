from __future__ import annotations

from pathlib import Path
from typing import Any, Iterator, Sequence

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
from mycli.types import ImageProtocol, OutputMode


class FakeDataFrame:
    written_paths: list[str] = []
    written_dataframes: list['FakeDataFrame'] = []

    def __init__(
        self,
        rows: list[tuple[Any, ...]] | list[Any],
        schema: list[str],
        orient: str | None = None,
    ) -> None:
        if orient is None:
            self.rows = [(value,) for value in rows]
        else:
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
    def __init__(
        self,
        name: str | Sequence[Any],
        values: list[Any] | None = None,
        *,
        strict: bool = True,
    ) -> None:
        if values is None:
            self.name = ''
            self.values = list(name)
        else:
            assert isinstance(name, str)
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


class ScalarConstructionFailingDataFrame(FakeDataFrame):
    def __init__(
        self,
        rows: list[tuple[Any, ...]] | list[Any],
        schema: list[str],
        orient: str | None = None,
    ) -> None:
        if orient is None:
            raise TypeError('invalid scalar')
        super().__init__(rows, schema, orient)


class ScalarConstructionFailingPolars:
    DataFrame = ScalarConstructionFailingDataFrame
    Series = FakeSeries


class SequenceConstructionFailingSeries(FakeSeries):
    def __init__(
        self,
        name: str | Sequence[Any],
        values: list[Any] | None = None,
        *,
        strict: bool = True,
    ) -> None:
        if values is None:
            raise TypeError('invalid sequence')
        super().__init__(name, values, strict=strict)


class SequenceConstructionFailingPolars:
    DataFrame = FakeDataFrame
    Series = SequenceConstructionFailingSeries


class FakeTopLevelMixin:
    pass


class FakePlot(FakeTopLevelMixin):
    formats: list[str] = []
    scale_factors: list[float] = []
    ppis: list[int] = []
    saved_paths: list[str] = []

    def __init__(self, _data: FakeDataFrame) -> None:
        self.save_calls: list[str] = []

    def save(self, file: Any, **kwargs: Any) -> None:
        self.save_calls.append(kwargs['format'])
        self.formats.append(kwargs['format'])
        if 'scale_factor' in kwargs:
            self.scale_factors.append(float(kwargs['scale_factor']))
        if 'ppi' in kwargs:
            self.ppis.append(kwargs['ppi'])
        if isinstance(file, str):
            self.saved_paths.append(file)
        else:
            file.write(b'png image')


class FailingPlot(FakeTopLevelMixin):
    def save(self, _file: Any, **_kwargs: str) -> None:
        raise OSError('renderer failed')


class FakeTheme:
    enabled: list[str] = []

    @classmethod
    def enable(cls, name: str) -> None:
        cls.enabled.append(name)


class FakeAltair:
    TopLevelMixin = FakeTopLevelMixin
    theme = FakeTheme

    @staticmethod
    def Plot(data: FakeDataFrame) -> FakePlot:
        return FakePlot(data)


class FailingAltair:
    TopLevelMixin = FakeTopLevelMixin
    theme = FakeTheme

    @staticmethod
    def Plot(_data: FakeDataFrame) -> FailingPlot:
        return FailingPlot()


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
        output_path=None,
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
        output_path=None,
        output_mode=output_mode,
    )


@pytest.mark.parametrize(
    ('command', 'expression', 'path'),
    [
        ('SELECT * FROM orders .> orders.parquet', None, 'orders.parquet'),
        ('SELECT * FROM orders .> orders.parquet;', None, 'orders.parquet'),
        (r'SELECT * FROM orders .> orders.parquet \g', None, 'orders.parquet'),
        ("SELECT * FROM orders .> 'order exports.parquet'", None, 'order exports.parquet'),
        ('SELECT * FROM orders .| df.head(10) .> orders.parquet', 'df.head(10)', 'orders.parquet'),
        ('SELECT * FROM orders .| alt.Plot(df) .> orders.png', 'alt.Plot(df)', 'orders.png'),
        (r"SELECT * FROM orders .| alt.Plot(df) .> 'order plot.png' \g", 'alt.Plot(df)', 'order plot.png'),
        ('SELECT * FROM orders .| alt.Plot(df) .> orders.pdf', 'alt.Plot(df)', 'orders.pdf'),
        (r"SELECT * FROM orders .| alt.Plot(df) .> 'order plot.SVG' \g", 'alt.Plot(df)', 'order plot.SVG'),
        (r"SELECT * FROM orders .| alt.Plot(df) .> 'order plot.HTML' \g", 'alt.Plot(df)', 'order plot.HTML'),
    ],
)
def test_parse_polars_transform_parses_file_redirect(
    command: str,
    expression: str | None,
    path: str,
) -> None:
    assert parse_polars_transform(command) == PolarsPipeline(
        sql='SELECT * FROM orders',
        expression=expression,
        output_path=path,
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
        ('SELECT 1 .> export.csv', 'end in ".parquet", ".png", ".pdf", ".svg", or ".html"'),
        ('SELECT 1 .> export file.parquet', 'must be quoted'),
        ('SELECT 1 .> export.parquet .| df', 'must follow'),
        ('SELECT 1 .| df .> export.parquet \\x', 'cannot use special display terminators'),
        ('SELECT 1 .| df .> export.parquet \\G', 'cannot use special display terminators'),
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


def test_parse_output_path_rejects_mismatched_quotes() -> None:
    with pytest.raises(PolarsTransformError, match='matching quotes'):
        polars_transform._parse_output_path("'orders.parquet")


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


def test_load_vl_convert_reports_missing_dependency(monkeypatch: pytest.MonkeyPatch) -> None:
    original_import = __import__

    def fail_vl_convert_import(name: str, *args: Any, **kwargs: Any) -> Any:
        if name == 'vl_convert':
            raise ImportError('not installed')
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr('builtins.__import__', fail_vl_convert_import)

    with pytest.raises(PolarsTransformError, match='requires vl-convert-python'):
        polars_transform._load_vl_convert()


def test_run_polars_transform_materializes_and_renders_returned_dataframe() -> None:
    result = run_polars_transform(
        make_transform('df'),
        iter([SQLResult(header=['id'], rows=[(1,), (2,)])]),
    )

    assert result == SQLResult(header=['id'], rows=[(1,), (2,)])


@pytest.mark.parametrize(
    ('expression', 'column_name', 'value'),
    [
        ('42', '42', 42),
        ("'total'", 'total', 'total'),
    ],
)
def test_run_polars_transform_coerces_scalar_to_dataframe(
    expression: str,
    column_name: str,
    value: Any,
) -> None:
    result = run_polars_transform(
        make_transform(expression),
        iter([SQLResult(header=['id'], rows=[(1,)])]),
    )

    assert result == SQLResult(header=[column_name], rows=[(value,)])


def test_run_polars_transform_reports_invalid_scalar() -> None:
    transform = PolarsTransform(
        sql='SELECT id FROM orders',
        expression='42',
        code=compile('42', '<test>', 'eval'),
        polars=ScalarConstructionFailingPolars,
        altair=None,
    )

    with pytest.raises(PolarsTransformError, match='Unable to render scalar as DataFrame: TypeError: invalid scalar'):
        run_polars_transform(
            transform,
            iter([SQLResult(header=['id'], rows=[(1,)])]),
        )


@pytest.mark.parametrize(
    ('expression', 'header', 'rows'),
    [
        ("{'id': [1, 2], 'name': ['one', 'two']}", ['id', 'name'], [(1, 'one'), (2, 'two')]),
        ("{'id': 1, 'name': 'one'}", ['id', 'name'], [(1, 'one')]),
        ('{}', [], []),
    ],
)
def test_run_polars_transform_coerces_dictionary_to_dataframe(
    expression: str,
    header: list[str],
    rows: list[tuple[Any, ...]],
) -> None:
    import polars as pl

    transform = PolarsTransform(
        sql='SELECT id FROM orders',
        expression=expression,
        code=compile(expression, '<test>', 'eval'),
        polars=pl,
        altair=None,
    )

    result = run_polars_transform(
        transform,
        iter([SQLResult(header=['id'], rows=[(1,)])]),
    )

    assert result == SQLResult(header=header, rows=rows)


def test_run_polars_transform_coerces_sequence_to_series() -> None:
    result = run_polars_transform(
        make_transform('[1, None, 3]'),
        iter([SQLResult(header=['id'], rows=[(1,)])]),
    )

    assert result == SQLResult(header=['value'], rows=[(1,), (None,), (3,)])


def test_run_polars_transform_reports_invalid_sequence() -> None:
    transform = PolarsTransform(
        sql='SELECT id FROM orders',
        expression='[1, 2]',
        code=compile('[1, 2]', '<test>', 'eval'),
        polars=SequenceConstructionFailingPolars,
        altair=None,
    )

    with pytest.raises(PolarsTransformError, match='Unable to render Sequence as Series: TypeError: invalid sequence'):
        run_polars_transform(
            transform,
            iter([SQLResult(header=['id'], rows=[(1,)])]),
        )


def test_run_polars_transform_returns_empty_result_for_none() -> None:
    result = run_polars_transform(
        make_transform('None'),
        iter([SQLResult(header=['id'], rows=[(1,)])]),
    )

    assert result == SQLResult()


def test_run_polars_transform_reports_unsupported_return_type() -> None:
    result = run_polars_transform(
        make_transform('object()'),
        iter([SQLResult(header=['id'], rows=[(1,)])]),
    )

    assert result.status_plain == "Nothing could be displayed for return type: <class 'object'>"


def test_run_polars_transform_reports_invalid_dictionary() -> None:
    import polars as pl

    expression = "{'id': [1, 2], 'name': ['one']}"
    transform = PolarsTransform(
        sql='SELECT id FROM orders',
        expression=expression,
        code=compile(expression, '<test>', 'eval'),
        polars=pl,
        altair=None,
    )

    with pytest.raises(PolarsTransformError, match='Unable to render dictionary as DataFrame'):
        run_polars_transform(
            transform,
            iter([SQLResult(header=['id'], rows=[(1,)])]),
        )


def test_run_polars_transform_writes_dictionary_to_parquet(tmp_path: Path) -> None:
    import polars as pl

    path = tmp_path / 'orders.parquet'
    expression = "{'id': [1, 2], 'name': ['one', 'two']}"
    transform = PolarsTransform(
        sql='SELECT id FROM orders',
        expression=expression,
        code=compile(expression, '<test>', 'eval'),
        polars=pl,
        altair=None,
    )

    result = run_polars_transform(
        transform,
        iter([SQLResult(header=['id'], rows=[(1,)])]),
        str(path),
    )

    assert result == SQLResult(status=f'Wrote 2 rows to {path}.')
    assert pl.read_parquet(path).to_dict(as_series=False) == {'id': [1, 2], 'name': ['one', 'two']}


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


def test_run_polars_transform_reports_disabled_altair_plot_output() -> None:
    result = run_polars_transform(
        make_transform('alt.Plot(df)'),
        iter([SQLResult(header=['id'], rows=[(1,)])]),
    )

    assert result.status_plain == 'image_protocol is unset in ~/.myclirc. Inline plotting is disabled.'


@pytest.mark.parametrize('image_protocol', ['iterm2', 'kitty'])
def test_run_polars_transform_renders_altair_plot_for_image_protocol(
    monkeypatch: pytest.MonkeyPatch,
    image_protocol: ImageProtocol,
) -> None:
    load_calls: list[None] = []
    FakePlot.scale_factors = []
    FakePlot.ppis = []
    FakeTheme.enabled = []
    monkeypatch.setattr(polars_transform, '_load_vl_convert', lambda: load_calls.append(None))

    result = run_polars_transform(
        make_transform('alt.Plot(df)'),
        iter([SQLResult(header=['id'], rows=[(1,)])]),
        image_protocol=image_protocol,
        plot_scale_factor=1.5,
        plot_ppi=144,
        plot_theme='dark',
    )

    assert load_calls == [None]
    assert FakePlot.scale_factors == [1.5]
    assert FakePlot.ppis == [144]
    assert FakeTheme.enabled == ['dark']
    assert result == SQLResult(image=b'png image', image_protocol=image_protocol)


@pytest.mark.parametrize(
    ('path', 'plot_format', 'expected_scale_factors', 'expected_ppis', 'expected_load_calls', 'output_kind'),
    [
        ('plot.png', 'png', [1.5], [144], [None], 'image'),
        ('plot.pdf', 'pdf', [1.5], [], [None], 'image'),
        ('plot.SVG', 'svg', [1.5], [], [None], 'image'),
        ('plot.html', 'html', [], [], [], 'document'),
    ],
)
def test_run_polars_transform_writes_altair_plot_to_file(
    monkeypatch: pytest.MonkeyPatch,
    path: str,
    plot_format: str,
    expected_scale_factors: list[float],
    expected_ppis: list[int],
    expected_load_calls: list[None],
    output_kind: str,
) -> None:
    load_calls: list[None] = []
    FakePlot.formats = []
    FakePlot.scale_factors = []
    FakePlot.ppis = []
    FakePlot.saved_paths = []
    FakeTheme.enabled = []
    monkeypatch.setattr(polars_transform, '_load_vl_convert', lambda: load_calls.append(None))

    result = run_polars_transform(
        make_transform('alt.Plot(df)'),
        iter([SQLResult(header=['id'], rows=[(1,)])]),
        path,
        image_protocol='none',
        plot_scale_factor=1.5,
        plot_ppi=144,
        plot_theme='dark',
    )

    assert result == SQLResult(status=f'Wrote {plot_format.upper()} {output_kind} to {path}.')
    assert load_calls == expected_load_calls
    assert FakePlot.formats == [plot_format]
    assert FakePlot.saved_paths == [path]
    assert FakePlot.scale_factors == expected_scale_factors
    assert FakePlot.ppis == expected_ppis
    assert FakeTheme.enabled == ['dark']


@pytest.mark.parametrize('plot_format', ['png', 'pdf', 'svg', 'html'])
def test_run_polars_transform_reports_altair_file_write_error(
    monkeypatch: pytest.MonkeyPatch,
    plot_format: str,
) -> None:
    monkeypatch.setattr(polars_transform, '_load_vl_convert', lambda: None)
    transform = PolarsTransform(
        sql='SELECT id FROM orders',
        expression='alt.Plot(df)',
        code=compile('alt.Plot(df)', '<test>', 'eval'),
        polars=FakePolars,
        altair=FailingAltair,
    )

    path = f'plot.{plot_format}'
    with pytest.raises(
        PolarsTransformError,
        match=f'Unable to write {plot_format.upper()} file "{path}": OSError: renderer failed',
    ):
        run_polars_transform(
            transform,
            iter([SQLResult(header=['id'], rows=[(1,)])]),
            path,
        )


def test_run_polars_transform_uses_integer_default_plot_ppi(monkeypatch: pytest.MonkeyPatch) -> None:
    FakePlot.ppis = []
    monkeypatch.setattr(polars_transform, '_load_vl_convert', lambda: None)

    run_polars_transform(
        make_transform('alt.Plot(df)'),
        iter([SQLResult(header=['id'], rows=[(1,)])]),
        image_protocol='kitty',
    )

    assert FakePlot.ppis == [200]


def test_run_polars_transform_reports_invalid_altair_theme(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(polars_transform, '_load_vl_convert', lambda: None)

    def fail_enable(_name: str) -> None:
        raise ValueError('unknown theme')

    monkeypatch.setattr(FakeTheme, 'enable', fail_enable)

    with pytest.raises(PolarsTransformError, match='Unable to enable Altair plot theme "not-a-theme": ValueError: unknown theme'):
        run_polars_transform(
            make_transform('alt.Plot(df)'),
            iter([SQLResult(header=['id'], rows=[(1,)])]),
            image_protocol='kitty',
            plot_theme='not-a-theme',
        )


def test_run_polars_transform_reports_altair_plot_render_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(polars_transform, '_load_vl_convert', lambda: None)
    transform = PolarsTransform(
        sql='SELECT id FROM orders',
        expression='alt.Plot(df)',
        code=compile('alt.Plot(df)', '<test>', 'eval'),
        polars=FakePolars,
        altair=FailingAltair,
    )

    with pytest.raises(PolarsTransformError, match='Unable to render Altair plot: OSError: renderer failed'):
        run_polars_transform(
            transform,
            iter([SQLResult(header=['id'], rows=[(1,)])]),
            image_protocol='iterm2',
        )


def test_run_polars_transform_reports_missing_altair_renderer(monkeypatch: pytest.MonkeyPatch) -> None:
    def fail_load() -> None:
        raise PolarsTransformError('Altair plot rendering requires vl-convert-python. Install mycli[dataframe].')

    monkeypatch.setattr(polars_transform, '_load_vl_convert', fail_load)

    with pytest.raises(PolarsTransformError, match='requires vl-convert-python'):
        run_polars_transform(
            make_transform('alt.Plot(df)'),
            iter([SQLResult(header=['id'], rows=[(1,)])]),
            image_protocol='iterm2',
        )


def test_run_polars_transform_rejects_altair_plot_parquet_output() -> None:
    with pytest.raises(PolarsTransformError, match='Altair plots can only be written'):
        run_polars_transform(
            make_transform('alt.Plot(df)'),
            iter([SQLResult(header=['id'], rows=[(1,)])]),
            'plot.parquet',
            image_protocol='iterm2',
        )


@pytest.mark.parametrize(
    ('expression', 'path', 'message'),
    [
        ('df', 'data.pdf', 'DataFrame results can only be written'),
        ("pl.Series('id', [1])", 'data.svg', 'Series results can only be written'),
        ('df', 'data.html', 'DataFrame results can only be written'),
    ],
)
def test_run_polars_transform_rejects_dataframe_and_series_plot_output(
    expression: str,
    path: str,
    message: str,
) -> None:
    with pytest.raises(PolarsTransformError, match=message):
        run_polars_transform(
            make_transform(expression),
            iter([SQLResult(header=['id'], rows=[(1,)])]),
            path,
        )


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
