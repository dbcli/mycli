import pytest

from mycli.packages.special import main as special_main
from mycli.packages.special import source


@pytest.mark.parametrize(
    ('arg', 'expected'),
    [
        ('query.sql', ('query.sql', False, False, False)),
        ('--special query.sql', ('query.sql', True, False, False)),
        ('--show query.sql', ('query.sql', False, True, False)),
        ('--page query.sql', ('query.sql', False, False, True)),
        ('--special --show --page query file.sql', ('query file.sql', True, True, True)),
        ('--page --show --special query file.sql', ('query file.sql', True, True, True)),
        ('--show --show query.sql', ('query.sql', False, True, False)),
        ('--page --page query.sql', ('query.sql', False, False, True)),
        ('--show', ('', False, True, False)),
    ],
)
def test_parse_source_arguments(arg: str, expected: tuple[str, bool, bool, bool]) -> None:
    assert source.parse_source_arguments(arg) == expected


@pytest.mark.parametrize(
    ('filename', 'expected'),
    [
        ('', ''),
        ('query.sql', 'query.sql'),
        ('"query file.sql"', 'query file.sql'),
        ("'query file.sql'", 'query file.sql'),
        ('prefix" query".sql', 'prefix query.sql'),
    ],
)
def test_parse_source_filename(filename: str, expected: str) -> None:
    assert source.parse_source_filename(filename) == expected


@pytest.mark.parametrize(
    'filename',
    [
        'query file.sql',
        r'query\ file.sql',
        '"first file.sql" second.sql',
    ],
)
def test_parse_source_filename_rejects_multiple_unquoted_arguments(filename: str) -> None:
    with pytest.raises(ValueError, match='filenames containing spaces must be quoted'):
        source.parse_source_filename(filename)


def test_parse_source_filename_rejects_unclosed_quote() -> None:
    with pytest.raises(ValueError, match='No closing quotation'):
        source.parse_source_filename('"query file.sql')


def test_parse_source_filename_rejects_missing_parsed_argument(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(source.shlex, 'split', lambda *_args, **_kwargs: [])

    with pytest.raises(ValueError, match='accepts exactly one filename'):
        source.parse_source_filename('query.sql')


def test_source_filename_whitespace_scanner_allows_escaped_non_whitespace() -> None:
    assert not source._has_unquoted_whitespace(r'query\name.sql')


def test_parse_source_filename_preserves_windows_backslashes(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(source, 'WIN', True)

    assert source.parse_source_filename(r'C:\queries\query.sql') == r'C:\queries\query.sql'
    assert source.parse_source_filename(r'"C:\my queries\query.sql"') == r'C:\my queries\query.sql'


@pytest.mark.parametrize(
    ('command', 'arg', 'expected'),
    [
        ('status', '', True),
        ('ping', '', True),
        ('connect', 'db', True),
        ('config', 'get main.prompt', True),
        ('config', 'edit', False),
        ('dsn', 'list', True),
        ('dsn', 'edit prod', False),
        ('favorite', 'list', True),
        ('favorite', 'eval report', False),
        ('pager', '', False),
        ('delimiter', '$$', False),
        ('plugin_command', '', False),
    ],
)
def test_source_special_command_policy(
    monkeypatch: pytest.MonkeyPatch,
    command: str,
    arg: str,
    expected: bool,
) -> None:
    monkeypatch.setattr(source, '_registered_special_command', lambda query: (command, arg))

    assert source.source_special_command_is_safe('/command') is expected


def test_registered_source_special_command_uses_case_insensitive_registry_lookup(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    registered = special_main.SpecialCommand(
        handler=lambda: None,
        command='status',
        usage='/status',
        description='Show status.',
        arg_type=special_main.ArgType.NO_ARGUMENT,
        hidden=False,
        case_sensitive=False,
        aliases=None,
        backslash_only=False,
    )
    monkeypatch.setattr(special_main, 'COMMANDS', {'/status': registered})

    assert source._registered_special_command('/STATUS verbose') == ('status', 'verbose')


def test_registered_source_special_command_rejects_unknown_command(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(special_main, 'COMMANDS', {})

    assert source._registered_special_command('/unknown') is None
    assert source.source_special_command_is_safe('/unknown') is False


@pytest.mark.parametrize('command', ['fd', 'fs'])
def test_source_special_command_policy_allows_favorite_aliases(
    monkeypatch: pytest.MonkeyPatch,
    command: str,
) -> None:
    monkeypatch.setattr(source, '_registered_special_command', lambda query: (command, 'report'))

    assert source.source_special_command_is_safe('/command') is True


@pytest.mark.parametrize(
    ('expanded_query', 'expected'),
    [
        ('select 1; select 2;', True),
        ('select 1; /system echo unsafe;', False),
        (None, True),
    ],
)
def test_favorite_source_command_requires_sql_only_expansion(
    monkeypatch: pytest.MonkeyPatch,
    expanded_query: str | None,
    expected: bool,
) -> None:
    monkeypatch.setattr(
        source,
        'expand_favorite_query',
        lambda arg: (expanded_query, None if expanded_query is not None else 'invalid arguments'),
    )

    assert source._favorite_source_command_is_safe('report') is expected


@pytest.mark.parametrize('command', ['f', 'favorite'])
def test_source_favorite_run_uses_expansion_policy(monkeypatch: pytest.MonkeyPatch, command: str) -> None:
    arg = 'report' if command == 'f' else 'run report'
    monkeypatch.setattr(source, '_registered_special_command', lambda query: (command, arg))
    monkeypatch.setattr(source, '_favorite_source_command_is_safe', lambda favorite_arg: False)

    assert source.source_special_command_is_safe('/favorite') is False
