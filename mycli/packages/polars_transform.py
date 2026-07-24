from __future__ import annotations

import builtins
from dataclasses import dataclass
from io import BytesIO
from types import CodeType
from typing import Any, Iterable

import sqlglot

from mycli.packages.special.delimitercommand import DelimiterCommand
from mycli.packages.sqlresult import SQLResult
from mycli.types import ImageProtocol, OutputMode

delimiter_command = DelimiterCommand()


class PolarsTransformError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class PolarsPipeline:
    sql: str
    expression: str | None
    parquet_path: str | None
    output_mode: OutputMode


@dataclass(frozen=True, slots=True)
class PolarsTransform:
    sql: str
    expression: str | None
    code: CodeType
    polars: Any
    altair: Any | None


def parse_polars_transform(command: str) -> PolarsPipeline | None:
    """Parse a SQL statement with optional Polars transform and Parquet output."""
    try:
        tokens = sqlglot.tokenize(command)
    except sqlglot.errors.TokenError as exc:
        raise PolarsTransformError(f'Unable to parse Polars transform: {exc}') from exc

    pipe_index: int | None = None
    parquet_index: int | None = None
    for index, token in enumerate(tokens[:-1]):
        following = tokens[index + 1]
        if token.token_type != sqlglot.TokenType.DOT:
            continue
        if token.start == 0 or not command[token.start - 1].isspace():
            continue
        if following.token_type not in (sqlglot.TokenType.PIPE, sqlglot.TokenType.GT):
            continue
        if following.end + 1 >= len(command):
            if following.token_type == sqlglot.TokenType.PIPE:
                raise PolarsTransformError('Polars transforms require a Python expression.')
            raise PolarsTransformError('Parquet saves require a destination path.')
        if not command[following.end + 1].isspace():
            continue
        if following.token_type == sqlglot.TokenType.PIPE:
            if pipe_index is not None:
                raise PolarsTransformError('Polars transforms support only one ".|" operator.')
            pipe_index = index
        else:
            if parquet_index is not None:
                raise PolarsTransformError('Parquet saves support only one ".>" operator.')
            parquet_index = index

    if pipe_index is None and parquet_index is None:
        return None
    if parquet_index is not None and pipe_index is not None and parquet_index < pipe_index:
        raise PolarsTransformError('The ".>" operator must follow the ".|" operator.')

    first_index = pipe_index if pipe_index is not None else parquet_index
    assert first_index is not None
    sql = command[: tokens[first_index].start].strip()
    expression: str | None = None
    parquet_path: str | None = None
    if pipe_index is not None:
        pipe_operator = tokens[pipe_index + 1]
        expression_end = tokens[parquet_index].start if parquet_index is not None else len(command)
        expression = command[pipe_operator.end + 1 : expression_end].strip()
    if parquet_index is not None:
        parquet_operator = tokens[parquet_index + 1]
        parquet_path = command[parquet_operator.end + 1 :].strip()
        parquet_path = parquet_path.removesuffix(delimiter_command.current).rstrip()
        parquet_path = parquet_path.removesuffix(r'\g').rstrip()

    has_display_terminator = any(value is not None and value.endswith((r'\x', r'\G')) for value in (sql, expression, parquet_path))
    if parquet_path is not None and has_display_terminator:
        raise PolarsTransformError('Parquet saves cannot use special display terminators.')
    if sql.endswith(r'\x') or expression is not None and expression.endswith(r'\x'):
        output_mode: OutputMode = 'explorer'
    elif sql.endswith(r'\G') or expression is not None and expression.endswith(r'\G'):
        output_mode = 'expanded'
    else:
        output_mode = 'tabular'

    for delimiter in (delimiter_command.current, r'\G', r'\g', r'\x'):
        sql = sql.removesuffix(delimiter).rstrip()
        if expression is not None:
            expression = expression.removesuffix(delimiter).rstrip()

    if not sql:
        raise PolarsTransformError('Polars transforms require a SQL statement.')
    if expression is not None and not expression:
        raise PolarsTransformError('Polars transforms require a Python expression.')
    if parquet_path is not None:
        if not parquet_path:
            raise PolarsTransformError('Parquet saves require a destination path.')
        parquet_path = _parse_parquet_path(parquet_path)
    _validate_sql(sql)
    return PolarsPipeline(sql=sql, expression=expression, parquet_path=parquet_path, output_mode=output_mode)


def _parse_parquet_path(path: str) -> str:
    if path[0] in ('\'', '"'):
        if len(path) < 2 or path[-1] != path[0]:
            raise PolarsTransformError('Parquet save paths must use matching quotes.')
        path = path[1:-1]
    elif any(character.isspace() for character in path):
        raise PolarsTransformError('Parquet save paths containing spaces must be quoted.')
    if not path.lower().endswith('.parquet'):
        raise PolarsTransformError('Parquet save paths must end in ".parquet".')
    return path


def _validate_sql(sql: str) -> None:
    try:
        statements = sqlglot.parse(sql, read='mysql')
    except sqlglot.errors.ParseError as exc:
        raise PolarsTransformError(f'Unable to parse SQL before Polars transform: {exc}') from exc
    if len(statements) != 1:
        raise PolarsTransformError('Polars transforms support exactly one SQL statement.')


def prepare_polars_transform(sql: str, expression: str | None) -> PolarsTransform:
    """Compile a transform expression and load its optional dependency."""
    try:
        code = (
            compile(expression, '<mycli Polars transform>', 'eval')
            if expression is not None
            else compile('df', '<mycli Polars transform>', 'eval')
        )
    except SyntaxError as exc:
        raise PolarsTransformError(f'Invalid Polars transform expression: "{expression}": {exc.msg}') from exc
    return PolarsTransform(
        sql=sql,
        expression=expression,
        code=code,
        polars=_load_polars(),
        altair=_load_altair() if expression is not None else None,
    )


def _load_polars() -> Any:
    try:
        import polars as pl
    except ImportError as exc:
        raise PolarsTransformError("Polars transforms require Polars to be installed.") from exc
    return pl


def _load_altair() -> Any:
    try:
        import altair as alt
    except ImportError as exc:
        raise PolarsTransformError("Polars transforms require Altair to be installed.") from exc
    return alt


def _load_vl_convert() -> None:
    try:
        import vl_convert  # noqa: F401
    except ImportError as exc:
        raise PolarsTransformError('Altair plot rendering requires vl-convert-python. Install mycli[dataframe].') from exc


def run_polars_transform(
    transform: PolarsTransform,
    results: Iterable[SQLResult],
    parquet_path: str | None = None,
    *,
    image_protocol: ImageProtocol = 'none',
    plot_scale_factor: float = 1.0,
    plot_ppi: int = 200,
    plot_theme: str = 'carbong90',
) -> SQLResult:
    iterator = iter(results)
    try:
        result = next(iterator)
    except StopIteration as exc:
        raise PolarsTransformError('Polars transforms require a tabular SQL result.') from exc
    try:
        next(iterator)
    except StopIteration:
        pass
    else:
        raise PolarsTransformError('Polars transforms do not support multiple result sets.')

    if not isinstance(result.header, list) or result.rows is None:
        raise PolarsTransformError('Polars transforms require a tabular SQL result.')

    dataframe = transform.polars.DataFrame(list(result.rows), schema=result.header, orient='row')
    try:
        value = eval(
            transform.code,
            {'__builtins__': builtins, 'df': dataframe, 'pl': transform.polars, 'alt': transform.altair},
        )
    except Exception as exc:
        raise PolarsTransformError(f'Polars expression failed: {type(exc).__name__}: {exc}') from exc
    if isinstance(value, transform.polars.DataFrame):
        if parquet_path is not None:
            try:
                value.write_parquet(parquet_path)
            except Exception as exc:
                raise PolarsTransformError(f'Unable to write Parquet file "{parquet_path}": {type(exc).__name__}: {exc}') from exc
            return SQLResult(status=f'Wrote {len(value)} rows to {parquet_path}.')
        return SQLResult(header=list(value.columns), rows=list(value.iter_rows()))
    if isinstance(value, transform.polars.Series):
        column_name = value.name or 'value'
        if parquet_path is not None:
            try:
                series_dataframe = value.rename(column_name).to_frame()
                series_dataframe.write_parquet(parquet_path)
            except Exception as exc:
                raise PolarsTransformError(f'Unable to write Parquet file "{parquet_path}": {type(exc).__name__}: {exc}') from exc
            return SQLResult(status=f'Wrote {len(series_dataframe)} rows to {parquet_path}.')
        return SQLResult(header=[column_name], rows=[(item,) for item in value])
    if transform.altair is not None and isinstance(value, transform.altair.TopLevelMixin):
        if parquet_path is not None:
            raise PolarsTransformError('Polars transforms must return a DataFrame or Series before writing Parquet output.')
        if image_protocol == 'none':
            return SQLResult(status='image_protocol is unset in ~/.myclirc. Inline plotting is disabled.')
        _load_vl_convert()
        png = BytesIO()
        try:
            transform.altair.theme.enable(plot_theme)
        except Exception as exc:
            raise PolarsTransformError(f'Unable to enable Altair plot theme "{plot_theme}": {type(exc).__name__}: {exc}') from exc
        try:
            value.save(
                png,
                format='png',
                scale_factor=plot_scale_factor,
                ppi=plot_ppi,
            )
        except Exception as exc:
            raise PolarsTransformError(f'Unable to render Altair chart: {type(exc).__name__}: {exc}') from exc
        return SQLResult(image=png.getvalue(), image_protocol=image_protocol)
    if parquet_path is not None:
        raise PolarsTransformError('Polars transforms must return a DataFrame or Series before writing Parquet output.')
    return SQLResult(status=f'Nothing could be displayed for return type: {type(value)}')
