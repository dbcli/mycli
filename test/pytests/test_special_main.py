import builtins
from collections.abc import Iterator
import importlib
import importlib.util
import sys
from types import ModuleType
from typing import Any, cast

import pytest

from mycli.constants import DOCS_URL, ISSUES_URL
from mycli.packages.special import main as special_main
from mycli.packages.sqlresult import SQLResult


@pytest.fixture
def restore_commands() -> Iterator[None]:
    original_commands = special_main.COMMANDS.copy()
    original_case_sensitive_commands = special_main.CASE_SENSITIVE_COMMANDS.copy()
    original_case_insensitive_commands = special_main.CASE_INSENSITIVE_COMMANDS.copy()
    try:
        yield
    finally:
        special_main.COMMANDS.clear()
        special_main.COMMANDS.update(original_commands)
        special_main.CASE_SENSITIVE_COMMANDS.clear()
        special_main.CASE_SENSITIVE_COMMANDS.update(original_case_sensitive_commands)
        special_main.CASE_INSENSITIVE_COMMANDS.clear()
        special_main.CASE_INSENSITIVE_COMMANDS.update(original_case_insensitive_commands)


class FakeHelpCursor:
    def __init__(self, responses: list[dict[str, Any]]) -> None:
        self._responses = responses
        self.calls: list[tuple[str, object]] = []
        self.description: list[tuple[str, object | None]] | None = None
        self.rowcount = 0

    def execute(self, query: str, params: object) -> None:
        self.calls.append((query, params))
        response = self._responses.pop(0)
        self.description = response['description']
        self.rowcount = response['rowcount']


def load_isolated_special_main(module_name: str) -> ModuleType:
    assert special_main.__file__ is not None
    spec = importlib.util.spec_from_file_location(module_name, special_main.__file__)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    try:
        spec.loader.exec_module(module)
    except Exception:
        sys.modules.pop(module_name, None)
        raise
    return module


@pytest.mark.parametrize(
    ('sql', 'expected'),
    [
        ('help select', ('help', special_main.CommandVerbosity.NORMAL, 'select')),
        (r'\llm+ prompt', (r'\llm', special_main.CommandVerbosity.VERBOSE, 'prompt')),
        (r'\llm- prompt', (r'\llm', special_main.CommandVerbosity.SUCCINCT, 'prompt')),
        ('help   spaced   ', ('help', special_main.CommandVerbosity.NORMAL, 'spaced')),
    ],
)
def test_parse_special_command(sql: str, expected: tuple[str, special_main.CommandVerbosity, str]) -> None:
    assert special_main.parse_special_command(sql) == expected


def test_register_special_command_adds_primary_and_alias_entries(restore_commands: None) -> None:
    def handler() -> None:
        return None

    special_main.COMMANDS.clear()
    special_main.register_special_command(
        handler,
        'Demo',
        'demo',
        'Description',
        aliases=['\\d'],
    )

    assert special_main.COMMANDS['demo'] == special_main.SpecialCommand(
        handler,
        'Demo',
        'demo',
        'Description',
        arg_type=special_main.ArgType.PARSED_QUERY,
        hidden=False,
        case_sensitive=False,
        shortcut='\\d',
    )
    assert special_main.COMMANDS['\\d'] == special_main.SpecialCommand(
        handler,
        'Demo',
        'demo',
        'Description',
        arg_type=special_main.ArgType.PARSED_QUERY,
        hidden=True,
        case_sensitive=False,
        shortcut=None,
    )


def test_register_special_command_tracks_case_insensitive_commands(restore_commands: None) -> None:
    special_main.COMMANDS.clear()
    special_main.CASE_SENSITIVE_COMMANDS.clear()
    special_main.CASE_INSENSITIVE_COMMANDS.clear()

    special_main.register_special_command(
        lambda: None,
        'Demo',
        'demo',
        'Description',
        aliases=['\\d'],
    )

    assert special_main.CASE_SENSITIVE_COMMANDS == set()
    assert special_main.CASE_INSENSITIVE_COMMANDS == {'demo', '\\d'}


def test_special_command_decorator_registers_case_sensitive_command(restore_commands: None) -> None:
    special_main.COMMANDS.clear()
    special_main.CASE_SENSITIVE_COMMANDS.clear()
    special_main.CASE_INSENSITIVE_COMMANDS.clear()

    @special_main.special_command('Camel', 'Camel', 'Description', case_sensitive=True)
    def handler() -> None:
        return None

    assert special_main.COMMANDS['Camel'].handler is handler
    assert 'Camel' in special_main.CASE_SENSITIVE_COMMANDS
    assert special_main.CASE_INSENSITIVE_COMMANDS == set()
    assert 'camel' not in special_main.COMMANDS


def test_execute_raises_when_command_is_missing() -> None:
    with pytest.raises(special_main.CommandNotFound, match='Command not found: missing'):
        special_main.execute(cast(Any, None), 'missing')


def test_execute_raises_for_case_sensitive_mismatch(restore_commands: None) -> None:
    special_main.COMMANDS.clear()
    special_main.register_special_command(lambda: None, 'Camel', 'Camel', 'Description', case_sensitive=True)

    with pytest.raises(special_main.CommandNotFound, match='Command not found: camel'):
        special_main.execute(cast(Any, None), 'camel')


def test_execute_raises_for_case_sensitive_alias_lookup(restore_commands: None) -> None:
    special_main.COMMANDS.clear()
    special_main.register_special_command(
        lambda: None,
        'Demo',
        'Demo',
        'Description',
        case_sensitive=True,
        aliases=['demo'],
    )

    with pytest.raises(special_main.CommandNotFound, match='Command not found: DEMO'):
        special_main.execute(cast(Any, None), 'DEMO')


def test_execute_raises_when_case_sensitive_exact_lookup_falls_back_to_lowercase(restore_commands: None) -> None:
    special_main.COMMANDS.clear()
    special_main.CASE_SENSITIVE_COMMANDS.clear()
    special_main.CASE_INSENSITIVE_COMMANDS.clear()
    special_main.COMMANDS['camel'] = special_main.SpecialCommand(
        lambda: None,
        'Camel',
        'Camel',
        'Description',
        arg_type=special_main.ArgType.NO_QUERY,
        hidden=False,
        case_sensitive=True,
        shortcut=None,
    )
    special_main.CASE_SENSITIVE_COMMANDS.add('Camel')

    with pytest.raises(special_main.CommandNotFound, match='Command not found: Camel'):
        special_main.execute(cast(Any, None), 'Camel')


def test_execute_dispatches_no_query_command(restore_commands: None) -> None:
    calls: list[str] = []

    def handler() -> list[SQLResult]:
        calls.append('called')
        return [SQLResult(status='ok')]

    special_main.COMMANDS.clear()
    special_main.register_special_command(
        handler,
        'demo',
        'demo',
        'Description',
        arg_type=special_main.ArgType.NO_QUERY,
    )

    assert special_main.execute(cast(Any, None), 'demo') == [SQLResult(status='ok')]
    assert calls == ['called']


def test_execute_uses_lowercase_lookup_for_case_insensitive_command(restore_commands: None) -> None:
    calls: list[str] = []

    def handler() -> list[SQLResult]:
        calls.append('called')
        return [SQLResult(status='ok')]

    special_main.COMMANDS.clear()
    special_main.register_special_command(
        handler,
        'demo',
        'demo',
        'Description',
        arg_type=special_main.ArgType.NO_QUERY,
    )

    assert special_main.execute(cast(Any, None), 'DEMO') == [SQLResult(status='ok')]
    assert calls == ['called']


def test_execute_dispatches_parsed_query_command(restore_commands: None) -> None:
    calls: list[tuple[object, str, bool]] = []

    def handler(*, cur: object, arg: str, command_verbosity: bool) -> list[SQLResult]:
        calls.append((cur, arg, command_verbosity))
        return [SQLResult(status='parsed')]

    special_main.COMMANDS.clear()
    special_main.register_special_command(
        handler,
        'demo',
        'demo',
        'Description',
        arg_type=special_main.ArgType.PARSED_QUERY,
    )

    cur = object()
    assert special_main.execute(cast(Any, cur), 'demo+ value') == [SQLResult(status='parsed')]
    assert calls == [(cur, 'value', True)]


def test_execute_dispatches_raw_query_command(restore_commands: None) -> None:
    calls: list[tuple[object, str]] = []

    def handler(*, cur: object, query: str) -> list[SQLResult]:
        calls.append((cur, query))
        return [SQLResult(status='raw')]

    special_main.COMMANDS.clear()
    special_main.register_special_command(
        handler,
        'demo',
        'demo',
        'Description',
        arg_type=special_main.ArgType.RAW_QUERY,
        case_sensitive=True,
    )

    cur = object()
    assert special_main.execute(cast(Any, cur), 'demo payload') == [SQLResult(status='raw')]
    assert calls == [(cur, 'demo payload')]


def test_execute_routes_help_with_argument_to_keyword_help(monkeypatch) -> None:
    calls: list[tuple[object, str]] = []

    def fake_show_keyword_help(cur: object, arg: str) -> list[SQLResult]:
        calls.append((cur, arg))
        return [SQLResult(status='keyword')]

    monkeypatch.setattr(special_main, 'show_keyword_help', fake_show_keyword_help)

    cur = object()
    assert special_main.execute(cast(Any, cur), 'help select') == [SQLResult(status='keyword')]
    assert calls == [(cur, 'select')]


def test_execute_routes_uppercase_help_with_argument_to_keyword_help(monkeypatch) -> None:
    calls: list[tuple[object, str]] = []

    def fake_show_keyword_help(cur: object, arg: str) -> list[SQLResult]:
        calls.append((cur, arg))
        return [SQLResult(status='keyword')]

    monkeypatch.setattr(special_main, 'show_keyword_help', fake_show_keyword_help)

    cur = object()
    assert special_main.execute(cast(Any, cur), 'HELP select') == [SQLResult(status='keyword')]
    assert calls == [(cur, 'select')]


def test_execute_raises_for_unknown_arg_type(restore_commands: None) -> None:
    special_main.COMMANDS.clear()
    special_main.CASE_SENSITIVE_COMMANDS.clear()
    special_main.CASE_INSENSITIVE_COMMANDS.clear()
    special_main.COMMANDS['demo'] = special_main.SpecialCommand(
        lambda: None,
        'demo',
        'demo',
        'Description',
        arg_type=cast(Any, object()),
        hidden=False,
        case_sensitive=False,
        shortcut=None,
    )
    special_main.CASE_INSENSITIVE_COMMANDS.add('demo')

    with pytest.raises(special_main.CommandNotFound, match='Command type not found: demo'):
        special_main.execute(cast(Any, None), 'demo')


def test_show_help_lists_only_visible_commands(restore_commands: None) -> None:
    special_main.COMMANDS.clear()
    special_main.register_special_command(lambda: None, 'visible', 'visible', 'Visible command', aliases=['\\v'])
    special_main.register_special_command(lambda: None, 'hidden', 'hidden', 'Hidden command', hidden=True)

    result = special_main.show_help()[0]

    assert result.header == ['Command', 'Shortcut', 'Usage', 'Description']
    assert result.rows == [('visible', '\\v', 'visible', 'Visible command')]
    assert result.postamble == f'Docs index — {DOCS_URL}'


def test_show_keyword_help_for_special_command(restore_commands: None) -> None:
    special_main.COMMANDS.clear()
    special_main.CASE_SENSITIVE_COMMANDS.clear()
    special_main.CASE_INSENSITIVE_COMMANDS.clear()
    special_main.register_special_command(lambda: None, 'demo', 'demo <arg>', 'Demo command')

    result = special_main.show_keyword_help(cast(Any, None), 'demo+')[0]

    assert result.header == ['name', 'description', 'example']
    assert result.rows == [('demo', 'demo <arg>\nDemo command', '')]


def test_show_keyword_help_for_case_sensitive_special_alias() -> None:
    result = special_main.show_keyword_help(cast(Any, None), r'\e')[0]

    assert result.header == ['name', 'description', 'example']
    assert result.rows == [
        (
            r'\e',
            '<query>\\edit | \\edit <filename>\nEdit query with editor (uses $VISUAL or $EDITOR).',
            '',
        )
    ]


def test_show_keyword_help_exact_match() -> None:
    cur = FakeHelpCursor([
        {'description': [('name', None)], 'rowcount': 1},
    ])

    result = special_main.show_keyword_help(cast(Any, cur), '"select"')[0]

    assert cur.calls == [('help %s', 'select')]
    assert result.header == ['name']
    assert cast(Any, result.rows) is cur


def test_show_keyword_help_similar_match() -> None:
    cur = FakeHelpCursor([
        {'description': None, 'rowcount': 0},
        {'description': [('name', None)], 'rowcount': 2},
    ])

    result = special_main.show_keyword_help(cast(Any, cur), "'select'")[0]

    assert cur.calls == [('help %s', 'select'), ('help %s', ('%select%',))]
    assert result.preamble == 'Similar terms:'
    assert result.header == ['name']
    assert cast(Any, result.rows) is cur


def test_show_keyword_help_no_match() -> None:
    cur = FakeHelpCursor([
        {'description': None, 'rowcount': 0},
        {'description': None, 'rowcount': 0},
    ])

    result = special_main.show_keyword_help(cast(Any, cur), 'missing')[0]

    assert result.status == 'No help found for "missing".'


def test_file_bug_opens_browser(monkeypatch) -> None:
    calls: list[str] = []
    monkeypatch.setattr(special_main.webbrowser, 'open_new_tab', lambda url: calls.append(url))

    result = special_main.file_bug()[0]

    assert calls == [ISSUES_URL]
    assert result.status == f'{ISSUES_URL} — press "New Issue"'


def test_quit_command_raises_eoferror() -> None:
    with pytest.raises(EOFError):
        special_main.quit_()


def test_stub_command_raises_not_implemented() -> None:
    with pytest.raises(NotImplementedError):
        special_main.stub()


def test_llm_stub_raises_not_implemented_when_present() -> None:
    if hasattr(special_main, 'llm_stub'):
        with pytest.raises(NotImplementedError):
            special_main.llm_stub()


def test_reload_special_main_without_llm_support(monkeypatch) -> None:
    with monkeypatch.context() as m:
        m.setenv('MYCLI_LLM_OFF', '1')
        isolated_main = load_isolated_special_main('test_special_main_without_llm')
        try:
            assert isolated_main.LLM_IMPORTED is False
            assert r'\llm' not in isolated_main.COMMANDS
            assert r'\ai' not in isolated_main.COMMANDS
        finally:
            sys.modules.pop('test_special_main_without_llm', None)


def test_reload_special_main_handles_llm_import_error(monkeypatch) -> None:
    original_import = builtins.__import__

    def fake_import(name, globals=None, locals=None, fromlist=(), level=0):  # noqa: A002
        if name == 'llm':
            raise ImportError('no llm')
        return original_import(name, globals, locals, fromlist, level)

    with monkeypatch.context() as m:
        m.delenv('MYCLI_LLM_OFF', raising=False)
        m.setattr(builtins, '__import__', fake_import)
        isolated_main = load_isolated_special_main('test_special_main_import_error')
        try:
            assert isolated_main.LLM_IMPORTED is False
            assert r'\llm' not in isolated_main.COMMANDS
            assert r'\ai' not in isolated_main.COMMANDS
        finally:
            sys.modules.pop('test_special_main_import_error', None)
