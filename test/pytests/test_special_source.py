import pytest

from mycli.packages.special import main as special_main
from mycli.packages.special import source


@pytest.mark.parametrize(
    ('arg', 'expected'),
    [
        ('query.sql', source.SourceArguments(filename='query.sql')),
        ('--special query.sql', source.SourceArguments(filename='query.sql', allow_special=True)),
        ('--show query.sql', source.SourceArguments(filename='query.sql', show_queries=True)),
        ('query.sql --show', source.SourceArguments(filename='query.sql', show_queries=True)),
        ('--page query.sql', source.SourceArguments(filename='query.sql', page_output=True)),
        (
            '--page query.sql --show --special',
            source.SourceArguments(filename='query.sql', allow_special=True, show_queries=True, page_output=True),
        ),
        ('--show --show query.sql', source.SourceArguments(filename='query.sql', show_queries=True)),
        ('--page --page query.sql', source.SourceArguments(filename='query.sql', page_output=True)),
        ('--show', source.SourceArguments(show_queries=True)),
        ('--throttle 0.25 query.sql', source.SourceArguments(filename='query.sql', throttle=0.25)),
        ('query.sql --throttle=1e-2', source.SourceArguments(filename='query.sql', throttle=0.01)),
        (
            '--throttle 1 --show query.sql --throttle=0.5',
            source.SourceArguments(filename='query.sql', show_queries=True, throttle=0.5),
        ),
        ('"query file.sql"', source.SourceArguments(filename='query file.sql')),
        (r'query\ file.sql', source.SourceArguments(filename='query file.sql')),
        ('prefix" query".sql', source.SourceArguments(filename='prefix query.sql')),
        ('-- --show', source.SourceArguments(filename='--show')),
        ('--help', source.SourceArguments(show_help=True)),
        ('--show --help ignored.sql', source.SourceArguments(show_help=True)),
        ('ignored.sql --help', source.SourceArguments(show_help=True)),
    ],
)
def test_parse_source_arguments(arg: str, expected: source.SourceArguments) -> None:
    assert source.parse_source_arguments(arg) == expected


@pytest.mark.parametrize(
    'arg',
    [
        '--throttle',
        '--throttle=',
        '--throttle nope query.sql',
    ],
)
def test_parse_source_arguments_rejects_invalid_throttle(arg: str) -> None:
    with pytest.raises(ValueError, match='float|Missing'):
        source.parse_source_arguments(arg)


@pytest.mark.parametrize(
    'arg',
    [
        'query file.sql',
        '"first file.sql" second.sql',
    ],
)
def test_parse_source_arguments_rejects_multiple_filenames(arg: str) -> None:
    with pytest.raises(ValueError, match='filenames containing spaces must be quoted'):
        source.parse_source_arguments(arg)


def test_parse_source_arguments_rejects_unclosed_quote() -> None:
    with pytest.raises(ValueError, match='No closing quotation'):
        source.parse_source_arguments('"query file.sql')


def test_parse_source_arguments_rejects_unknown_option(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(ValueError, match=r'Unrecognized /source option: --unknown\. See /source --help\.'):
        source.parse_source_arguments('--unknown query.sql')

    assert capsys.readouterr() == ('', '')


def test_parse_source_arguments_does_not_abbreviate_options() -> None:
    with pytest.raises(ValueError, match=r'Unrecognized /source option: --spec\.'):
        source.parse_source_arguments('--spec query.sql')


def test_source_argument_parser_converts_other_errors() -> None:
    with pytest.raises(ValueError, match=r'Invalid /source arguments: unexpected\.'):
        source._SOURCE_ARGUMENT_PARSER.error('unexpected')


def test_parse_source_arguments_preserves_windows_backslashes(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(source, 'WIN', True)

    assert source.parse_source_arguments(r'C:\queries\query.sql').filename == r'C:\queries\query.sql'
    assert source.parse_source_arguments(r'"C:\my queries\query.sql"').filename == r'C:\my queries\query.sql'


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
