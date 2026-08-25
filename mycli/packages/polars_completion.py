from __future__ import annotations

import ast
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from functools import lru_cache
import inspect
from io import StringIO
import re
import sys
import tokenize
from types import ModuleType, UnionType
from typing import Any, Union, cast, get_args, get_origin

import sqlglot

from mycli.packages.polars_transform import _pipeline_operator_indexes

_ATTRIBUTE_PATTERN = re.compile(r'(?s)(.*)\.([A-Za-z_][A-Za-z0-9_]*)?\s*$')
_ANNOTATION_NAME_PATTERN = re.compile(r'[A-Za-z_][A-Za-z0-9_]*')
_SENTINEL = '__mycli_polars_completion__'
_OPEN_TO_CLOSE = {'(': ')', '[': ']', '{': '}'}
_CLOSE = frozenset(_OPEN_TO_CLOSE.values())


@dataclass(frozen=True, slots=True)
class PolarsCompletion:
    text: str
    display: str
    display_meta: str
    start_position: int


def complete_polars_transform(command: str) -> list[PolarsCompletion] | None:
    """Return safe attribute completions for a Polars transform expression."""
    try:
        tokens = sqlglot.tokenize(command)
        pipe_index, output_index = _pipeline_operator_indexes(command, tokens, require_operands=False)
    except sqlglot.errors.TokenError:
        return None
    if pipe_index is None:
        return None
    if output_index is not None:
        return []

    pipe = tokens[pipe_index + 1]
    expression = command[pipe.end + 1 :].strip()
    match = _ATTRIBUTE_PATTERN.fullmatch(expression)
    if match is None:
        return []
    prefix = match.group(2) or ''
    source = f'{match.group(1)}.{_SENTINEL}'
    closed_source = _close_open_delimiters(source)
    if closed_source is None:
        return []
    try:
        parsed = ast.parse(closed_source, mode='eval')
    except SyntaxError:
        return []
    target = next(
        (node for node in ast.walk(parsed) if isinstance(node, ast.Attribute) and node.attr == _SENTINEL),
        None,
    )
    if target is None:
        return []

    polars = _load_polars()
    if polars is None:
        return []
    owner = _infer_type(target.value, polars)
    if owner is None:
        return []
    return [
        PolarsCompletion(
            text=f'{name}(' if is_callable else name,
            display=name,
            display_meta=metadata,
            start_position=-len(prefix),
        )
        for name, is_callable, metadata in _members(owner, polars)
        if name.startswith(prefix)
    ]


def _close_open_delimiters(source: str) -> str | None:
    stack: list[str] = []
    try:
        tokens = tokenize.generate_tokens(StringIO(source).readline)
        for token in tokens:
            if token.type != tokenize.OP:
                continue
            if token.string in _OPEN_TO_CLOSE:
                stack.append(token.string)
            elif token.string in _CLOSE:
                if not stack or _OPEN_TO_CLOSE[stack.pop()] != token.string:
                    return None
    except (IndentationError, tokenize.TokenError):
        pass
    return source + ''.join(_OPEN_TO_CLOSE[value] for value in reversed(stack))


@lru_cache(maxsize=1)
def _load_polars() -> Any | None:
    try:
        import polars as pl
    except ImportError:
        return None
    return pl


def _infer_type(node: ast.AST, polars: Any) -> Any | None:
    if isinstance(node, ast.Name):
        if node.id == 'df':
            return polars.DataFrame
        if node.id == 'pl':
            return polars
        return None
    if isinstance(node, ast.Subscript):
        owner = _infer_type(node.value, polars)
        if owner is polars.DataFrame:
            return polars.Series
        if owner is polars.Expr:
            return polars.Expr
        return None
    if isinstance(node, ast.Attribute):
        owner = _infer_type(node.value, polars)
        member = _static_member(owner, node.attr)
        if member is None:
            return None
        if isinstance(member, property):
            return _return_type(member.fget, owner, polars)
        if inspect.isclass(member) or isinstance(member, ModuleType):
            return member
        return None
    if isinstance(node, ast.Call):
        if isinstance(node.func, ast.Attribute):
            owner = _infer_type(node.func.value, polars)
            member = _static_member(owner, node.func.attr)
            return _call_return_type(member, owner, polars)
        return None
    if isinstance(node, (ast.BinOp, ast.BoolOp, ast.Compare, ast.UnaryOp)):
        inferred = [_infer_type(child, polars) for child in ast.iter_child_nodes(node)]
        if polars.Expr in inferred:
            return polars.Expr
        if polars.Series in inferred:
            return polars.Series
    return None


def _static_member(owner: Any | None, name: str) -> Any | None:
    if owner is None:
        return None
    try:
        member = inspect.getattr_static(owner, name)
    except AttributeError:
        return None
    if isinstance(member, (classmethod, staticmethod)):
        return member.__func__
    return member


def _call_return_type(member: Any | None, owner: Any, polars: Any) -> Any | None:
    if member is None:
        return None
    if inspect.isclass(member):
        return member
    result = _return_type(member, owner, polars)
    if result is not None:
        return result
    call = _static_member(type(member), '__call__')
    return _return_type(call, owner, polars)


def _return_type(callable_object: Any | None, owner: Any, polars: Any) -> Any | None:
    if callable_object is None:
        return None
    if inspect.isroutine(callable_object):
        annotations = getattr(callable_object, '__annotations__', {})
    else:
        try:
            annotations = inspect.getattr_static(callable_object, '__annotations__')
        except AttributeError:
            annotations = {}
    if not isinstance(annotations, Mapping):
        return None
    annotation = annotations.get('return')
    if annotation is None or annotation is inspect.Signature.empty:
        return None
    if annotation is Any:
        return None
    if inspect.isclass(annotation):
        return annotation if _is_polars_type(annotation) else None
    arguments = get_args(annotation)
    if arguments:
        origin = cast(Any, get_origin(annotation))
        if origin not in (Union, UnionType):
            return None
        for argument in arguments:
            resolved = _resolve_annotation(argument, callable_object, owner, polars)
            if resolved is not None:
                return resolved
    return _resolve_annotation(annotation, callable_object, owner, polars)


def _resolve_annotation(annotation: Any, callable_object: Any, owner: Any, polars: Any) -> Any | None:
    if inspect.isclass(annotation):
        return annotation if _is_polars_type(annotation) else None
    if not isinstance(annotation, str):
        return None
    if annotation in ('Self', 'typing.Self'):
        return owner
    if '[' in annotation:
        return None
    namespace = getattr(callable_object, '__globals__', {}) if inspect.isroutine(callable_object) else {}
    for name in _ANNOTATION_NAME_PATTERN.findall(annotation):
        candidate = namespace.get(name)
        if not inspect.isclass(candidate):
            candidate = _static_member(polars, name)
        if not inspect.isclass(candidate):
            candidate = _polars_types_by_name(polars).get(name)
        if inspect.isclass(candidate) and _is_polars_type(candidate):
            return candidate
    return None


def _is_polars_type(value: type[Any]) -> bool:
    return value.__module__ == 'polars' or value.__module__.startswith('polars.')


@lru_cache(maxsize=1)
def _polars_types_by_name(polars: Any) -> Mapping[str, type[Any]]:
    """Index classes in loaded Polars modules without importing annotation paths."""
    candidates: dict[str, type[Any] | None] = {}
    modules = [
        module
        for module_name, module in tuple(sys.modules.items())
        if module is not None and (module is polars or module_name.startswith('polars.'))
    ]
    for module in modules:
        for value in vars(module).values():
            if not inspect.isclass(value) or not _is_polars_type(value):
                continue
            name = value.__name__
            existing = candidates.get(name, value)
            candidates[name] = value if existing is value else None
    return {name: value for name, value in candidates.items() if value is not None}


@lru_cache(maxsize=None)
def _members(owner: Any, polars: Any) -> tuple[tuple[str, bool, str], ...]:
    members: list[tuple[str, bool, str]] = []
    for name in dir(owner):
        if name.startswith('_'):
            continue
        member = _static_member(owner, name)
        if member is None:
            continue
        if isinstance(member, property):
            members.append((name, False, _property_metadata(member, owner, polars)))
        elif callable(member):
            members.append((name, True, _signature_metadata(member)))
    return tuple(members)


def _property_metadata(member: property, owner: Any, polars: Any) -> str:
    result = _return_type(member.fget, owner, polars)
    return result.__name__ if inspect.isclass(result) else 'property'


def _signature_metadata(member: Callable[..., Any]) -> str:
    callable_object: Any = member
    try:
        signature = inspect.signature(callable_object)
    except (TypeError, ValueError):
        callable_object = _static_member(type(member), '__call__')
        try:
            signature = inspect.signature(callable_object)
        except (TypeError, ValueError):
            return '()'
    parameters = [parameter for parameter in signature.parameters.values() if parameter.name not in ('self', 'cls')]
    rendered: list[str] = []
    for parameter in parameters[:4]:
        text = parameter.name
        if parameter.kind == inspect.Parameter.VAR_POSITIONAL:
            text = f'*{text}'
        elif parameter.kind == inspect.Parameter.VAR_KEYWORD:
            text = f'**{text}'
        elif parameter.default is not inspect.Parameter.empty:
            text = f'{text}=...'
        rendered.append(text)
    if len(parameters) > 4:
        rendered.append('...')
    return f"({', '.join(rendered)})"
