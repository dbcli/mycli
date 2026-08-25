from __future__ import annotations

import ast
import builtins
from typing import Any

from prompt_toolkit.completion import CompleteEvent
from prompt_toolkit.document import Document
import pytest
import sqlglot

from mycli.packages import polars_completion
from mycli.packages.polars_completion import PolarsCompletion, complete_polars_transform
from mycli.sqlcompleter import SQLCompleter


def completion(command: str, text: str) -> PolarsCompletion:
    candidates = complete_polars_transform(command)
    assert candidates is not None
    return next(candidate for candidate in candidates if candidate.text == text)


def test_completion_returns_none_outside_polars_transform() -> None:
    assert complete_polars_transform("SELECT '.| df.fi'") is None


def test_completion_offers_dataframe_methods() -> None:
    candidate = completion('SELECT * FROM orders .| df.fi', 'filter(')

    assert candidate.display == 'filter'
    assert candidate.display_meta == '(*predicates, **constraints)'
    assert candidate.start_position == -2


def test_completion_offers_polars_functions_in_unclosed_call() -> None:
    candidate = completion('SELECT * FROM orders .| df.filter(pl.c', 'col(')

    assert candidate.display == 'col'
    assert candidate.display_meta == '(name, *more_names)'
    assert candidate.start_position == -1


def test_completion_infers_dataframe_method_return_type() -> None:
    candidate = completion('SELECT * FROM orders .| df.filter(pl.col("id") > 1).he', 'head(')

    assert candidate.display_meta == '(n=...)'


@pytest.mark.parametrize(
    'expression',
    (
        'pl.col("name").str.to_',
        'df["name"].str.to_',
    ),
)
def test_completion_infers_expression_and_series_namespaces(expression: str) -> None:
    assert completion(f'SELECT * FROM orders .| {expression}', 'to_uppercase(').start_position == -3


def test_completion_infers_lazyframe_methods() -> None:
    assert completion('SELECT * FROM orders .| df.lazy().co', 'collect(').display == 'collect'


@pytest.mark.parametrize(
    ('expression', 'candidate'),
    (
        ('df.group_by_dynamic("timestamp", every="1d").a', 'agg('),
        ('df.rolling("timestamp", period="1d").a', 'agg('),
        ('pl.when(pl.col("value") > 0).then(1).o', 'otherwise('),
        ('df.plot.b', 'bar('),
        ('df["value"].plot.h', 'hist('),
    ),
)
def test_completion_resolves_forward_declared_polars_types(expression: str, candidate: str) -> None:
    assert completion(f'SELECT * FROM orders .| {expression}', candidate).display == candidate.removesuffix('(')


def test_completion_does_not_evaluate_expression(monkeypatch: pytest.MonkeyPatch) -> None:
    def fail_eval(*args: Any, **kwargs: Any) -> Any:
        raise AssertionError('User expression was evaluated.')

    monkeypatch.setattr(builtins, 'eval', fail_eval)

    candidate = completion('SELECT 1 .| pl.when(danger()).then(1).o', 'otherwise(')
    assert candidate.display == 'otherwise'


def test_completion_does_not_treat_generic_return_as_element_type() -> None:
    assert complete_polars_transform('SELECT * FROM orders .| df.get_columns().he') == []


def test_completion_does_not_add_parenthesis_to_property() -> None:
    candidate = completion('SELECT * FROM orders .| df.col', 'columns')

    assert candidate.display_meta == 'property'


def test_completion_excludes_private_members() -> None:
    candidates = complete_polars_transform('SELECT * FROM orders .| df._')

    assert candidates == []


@pytest.mark.parametrize(
    'command',
    (
        'SELECT * FROM orders .| df',
        'SELECT * FROM orders .| unknown.fi',
        'SELECT * FROM orders .| unknown().fi',
        'SELECT * FROM orders .| df.fi .> output.parquet',
        'SELECT * FROM orders .| df.fi .>',
    ),
)
def test_completion_suppresses_sql_candidates_in_uncompletable_transform(command: str) -> None:
    assert complete_polars_transform(command) == []


def test_completion_handles_missing_optional_dependency(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(polars_completion, '_load_polars', lambda: None)

    assert complete_polars_transform('SELECT * FROM orders .| df.fi') == []


def test_completion_handles_sqlglot_token_error(monkeypatch: pytest.MonkeyPatch) -> None:
    def raise_token_error(command: str) -> list[sqlglot.Token]:
        raise sqlglot.errors.TokenError(command)

    monkeypatch.setattr(polars_completion.sqlglot, 'tokenize', raise_token_error)

    assert complete_polars_transform('SELECT 1 .| df.fi') is None


@pytest.mark.parametrize('closed_source', (None, 'not valid Python!'))
def test_completion_handles_invalid_balanced_expression(
    monkeypatch: pytest.MonkeyPatch,
    closed_source: str | None,
) -> None:
    monkeypatch.setattr(polars_completion, '_close_open_delimiters', lambda source: closed_source)

    assert complete_polars_transform('SELECT 1 .| df.fi') == []


def test_completion_handles_missing_sentinel_node(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(polars_completion.ast, 'walk', lambda node: [])

    assert complete_polars_transform('SELECT 1 .| df.fi') == []


def test_close_open_delimiters_rejects_mismatched_delimiters() -> None:
    assert polars_completion._close_open_delimiters('df[(])') is None


def test_load_polars_returns_none_when_dependency_is_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    original_import = builtins.__import__

    def missing_polars(name: str, *args: Any, **kwargs: Any) -> Any:
        if name == 'polars':
            raise ImportError
        return original_import(name, *args, **kwargs)

    polars_completion._load_polars.cache_clear()
    monkeypatch.setattr(builtins, '__import__', missing_polars)
    assert polars_completion._load_polars() is None
    polars_completion._load_polars.cache_clear()


@pytest.mark.parametrize(
    ('expression', 'expected_name'),
    (
        ('pl.col("name")[0]', 'Expr'),
        ('pl[0]', None),
        ('df.missing', None),
        ('pl.DataFrame', 'DataFrame'),
        ('df.filter', None),
        ('unknown()', None),
        ('pl.col("name") + 1', 'Expr'),
        ('df["name"] + 1', 'Series'),
        ('1 + 2', None),
    ),
)
def test_infer_type_handles_static_expression_forms(expression: str, expected_name: str | None) -> None:
    import polars as pl

    inferred = polars_completion._infer_type(ast.parse(expression, mode='eval').body, pl)

    assert getattr(inferred, '__name__', None) == expected_name


def test_static_member_handles_absent_owner_and_attribute() -> None:
    assert polars_completion._static_member(None, 'value') is None
    assert polars_completion._static_member(object, 'missing') is None


def test_call_return_type_handles_missing_member_and_class() -> None:
    import polars as pl

    assert polars_completion._call_return_type(None, pl, pl) is None
    assert polars_completion._call_return_type(pl.DataFrame, pl, pl) is pl.DataFrame


def test_return_type_handles_annotation_variants() -> None:
    import polars as pl

    class InvalidAnnotations:
        __annotations__ = 1  # type: ignore[assignment]

    def returns_any() -> Any:
        raise AssertionError

    def returns_int() -> int:
        raise AssertionError

    def returns_generic() -> list[pl.Series]:
        raise AssertionError

    def returns_union() -> int | pl.DataFrame:
        raise AssertionError

    returns_any.__annotations__['return'] = Any
    returns_int.__annotations__['return'] = int
    returns_generic.__annotations__['return'] = list[pl.Series]
    returns_union.__annotations__['return'] = int | pl.DataFrame

    assert polars_completion._return_type(None, pl, pl) is None
    assert polars_completion._return_type(InvalidAnnotations(), pl, pl) is None
    assert polars_completion._return_type(returns_any, pl, pl) is None
    assert polars_completion._return_type(returns_int, pl, pl) is None
    assert polars_completion._return_type(returns_generic, pl, pl) is None
    assert polars_completion._return_type(returns_union, pl, pl) is pl.DataFrame


def test_resolve_annotation_handles_direct_self_and_invalid_annotations() -> None:
    import polars as pl

    assert polars_completion._resolve_annotation(pl.Expr, lambda: None, pl.DataFrame, pl) is pl.Expr
    assert polars_completion._resolve_annotation(object(), lambda: None, pl.DataFrame, pl) is None
    assert polars_completion._resolve_annotation('Self', lambda: None, pl.DataFrame, pl) is pl.DataFrame


def test_signature_metadata_handles_uninspectable_callable(monkeypatch: pytest.MonkeyPatch) -> None:
    def fail_signature(member: Any) -> Any:
        raise ValueError(member)

    monkeypatch.setattr(polars_completion.inspect, 'signature', fail_signature)

    assert polars_completion._signature_metadata(lambda: None) == '()'


@pytest.mark.parametrize('smart_completion', (True, False))
def test_sqlcompleter_uses_polars_completion_in_all_modes(smart_completion: bool) -> None:
    completer = SQLCompleter(smart_completion=smart_completion)
    document = Document('SELECT * FROM orders .| df.fi')

    candidates = list(completer.get_completions(document, CompleteEvent()))
    candidate = next(candidate for candidate in candidates if candidate.text == 'filter(')

    assert candidate.start_position == -2
    assert candidate.display_text == 'filter'
    assert candidate.display_meta_text == '(*predicates, **constraints)'
