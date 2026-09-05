import argparse
from dataclasses import dataclass
import shlex
from typing import Any, NoReturn

import sqlparse

from mycli.compat import WIN
from mycli.packages import special
from mycli.packages.special import main as special_main
from mycli.packages.special.iocommands import expand_favorite_query

INVALID_SOURCE_FILENAME = 'Source accepts exactly one filename; filenames containing spaces must be quoted.'
SOURCE_BOOLEAN_OPTIONS = ('--special', '--show', '--page')
SOURCE_OPTIONS = (*SOURCE_BOOLEAN_OPTIONS, '--throttle', '--help')
SOURCE_HELP_ROWS = [
    ('--special', 'Allow supported special /commands in the source file.'),
    ('--show', 'Show each statement before executing it.'),
    ('--page', 'Display all source output using the pager.'),
    (
        '--throttle <float>, --throttle=<float>',
        'Seconds to wait between executing statements.',
    ),
    ('--help', 'Show this help.'),
    ('<filename>', 'File containing SQL to execute.'),
]
SOURCE_SAFE_SPECIAL_COMMANDS = frozenset({
    'connect',
    'fd',
    'fs',
    'help',
    'l',
    'nowarnings',
    'ping',
    'prompt',
    'redirectformat',
    'rehash',
    'status',
    'tableformat',
    'timing',
    'use',
    'warnings',
    'dt',
})
SOURCE_SAFE_SUBCOMMANDS = {
    'config': frozenset({'help', 'get', 'search'}),
    'dsn': frozenset({'help', 'list', 'show', 'save', 'delete'}),
    'favorite': frozenset({'help', 'list', 'reload', 'run', 'save', 'delete'}),
}


@dataclass(frozen=True)
class SourceArguments:
    filename: str = ''
    allow_special: bool = False
    show_queries: bool = False
    page_output: bool = False
    throttle: float = 0.0
    show_help: bool = False


class _SourceHelpRequested(Exception):
    pass


class _SourceHelpAction(argparse.Action):
    def __call__(
        self,
        parser: argparse.ArgumentParser,
        namespace: argparse.Namespace,
        values: Any,
        option_string: str | None = None,
    ) -> NoReturn:
        raise _SourceHelpRequested


class _SourceArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> NoReturn:
        throttle_prefix = 'argument --throttle: '
        if message == f'{throttle_prefix}expected one argument':
            raise ValueError('Missing value for --throttle.')
        if message.startswith(throttle_prefix):
            raise ValueError(message.removeprefix(throttle_prefix))
        if message.startswith('unrecognized arguments:'):
            arguments = message.removeprefix('unrecognized arguments:').strip().split()
            unknown_option = next((argument for argument in arguments if argument.startswith('-')), None)
            if unknown_option is not None:
                raise ValueError(f'Unrecognized /source option: {unknown_option}. See /source --help.')
            raise ValueError(INVALID_SOURCE_FILENAME)
        raise ValueError(f'Invalid /source arguments: {message}.')


def _registered_special_command(query: str) -> tuple[str, str] | None:
    command, _verbosity, arg = special.parse_special_command(query)
    registered = special_main.COMMANDS.get(command)
    if registered is None:
        registered = special_main.COMMANDS.get(command.lower())
    if registered is None:
        return None
    return registered.command.removeprefix('\\').removeprefix('/').lower(), arg


def _favorite_source_command_is_safe(arg: str) -> bool:
    query, _error = expand_favorite_query(arg)
    if query is None:
        return True
    return not any(special.is_special_command(statement.rstrip(';')) for statement in sqlparse.split(query))


def _create_source_argument_parser() -> _SourceArgumentParser:
    parser = _SourceArgumentParser(prog='/source', add_help=False, allow_abbrev=False)
    parser.add_argument('--special', dest='allow_special', action='store_true')
    parser.add_argument('--show', dest='show_queries', action='store_true')
    parser.add_argument('--page', dest='page_output', action='store_true')
    parser.add_argument('--throttle', type=float, default=0.0)
    parser.add_argument('--help', nargs=0, action=_SourceHelpAction)
    parser.add_argument('filename', nargs='?')
    return parser


_SOURCE_ARGUMENT_PARSER = _create_source_argument_parser()


def parse_source_arguments(arg: str) -> SourceArguments:
    try:
        arguments = shlex.split(arg, posix=not WIN)
    except ValueError as error:
        raise ValueError(f'Invalid source filename: {error}.') from None
    try:
        parsed = _SOURCE_ARGUMENT_PARSER.parse_args(arguments)
    except _SourceHelpRequested:
        return SourceArguments(show_help=True)

    filename = parsed.filename or ''
    if WIN and len(filename) >= 2 and filename[0] == filename[-1] and filename[0] in ("'", '"'):
        filename = filename[1:-1]
    return SourceArguments(
        filename=filename,
        allow_special=parsed.allow_special,
        show_queries=parsed.show_queries,
        page_output=parsed.page_output,
        throttle=parsed.throttle,
    )


def source_special_command_is_safe(query: str) -> bool:
    parsed = _registered_special_command(query)
    if parsed is None:
        return False

    command, arg = parsed
    if command == 'f':
        return not arg or _favorite_source_command_is_safe(arg)
    if command in ('fd', 'fs'):
        return True
    if command in SOURCE_SAFE_SPECIAL_COMMANDS:
        return True

    subcommands = SOURCE_SAFE_SUBCOMMANDS.get(command)
    if subcommands is None:
        return False
    arguments = arg.split(maxsplit=1)
    subcommand = arguments[0].lower() if arguments else 'help'
    if subcommand not in subcommands:
        return False
    if command == 'favorite' and subcommand == 'run':
        run_arg = arguments[1] if len(arguments) == 2 else ''
        return not run_arg or _favorite_source_command_is_safe(run_arg)
    return True
