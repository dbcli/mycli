import math
import shlex

import sqlparse

from mycli.compat import WIN
from mycli.packages import special
from mycli.packages.special import main as special_main
from mycli.packages.special.iocommands import expand_favorite_query

INVALID_SOURCE_FILENAME = 'Source accepts exactly one filename; filenames containing spaces must be quoted.'
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


def _has_unquoted_whitespace(value: str) -> bool:
    quote: str | None = None
    escaped = False
    for character in value:
        if escaped:
            if quote is None and character.isspace():
                return True
            escaped = False
            continue
        if not WIN and character == '\\' and quote != "'":
            escaped = True
            continue
        if character in ("'", '"'):
            if quote is None:
                quote = character
            elif quote == character:
                quote = None
        elif quote is None and character.isspace():
            return True
    return False


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


def _parse_throttle(value: str) -> float:
    if not value:
        raise ValueError('Missing value for --throttle.')
    try:
        throttle = float(value)
    except ValueError:
        raise ValueError(f'Invalid --throttle value: {value}. Expected a finite, non-negative number.') from None
    if not math.isfinite(throttle) or throttle < 0:
        raise ValueError(f'Invalid --throttle value: {value}. Expected a finite, non-negative number.')
    return throttle


def parse_source_arguments(arg: str) -> tuple[str, bool, bool, bool, float]:
    allow_special = False
    show_queries = False
    page_output = False
    throttle = 0.0
    filename = arg
    while arguments := filename.split(maxsplit=1):
        if arguments[0] == '--special':
            allow_special = True
        elif arguments[0] == '--show':
            show_queries = True
        elif arguments[0] == '--page':
            page_output = True
        elif arguments[0] == '--throttle':
            if len(arguments) != 2:
                raise ValueError('Missing value for --throttle.')
            throttle_arguments = arguments[1].split(maxsplit=1)
            throttle = _parse_throttle(throttle_arguments[0])
            filename = throttle_arguments[1] if len(throttle_arguments) == 2 else ''
            continue
        elif arguments[0].startswith('--throttle='):
            throttle = _parse_throttle(arguments[0].partition('=')[2])
        else:
            break
        filename = arguments[1] if len(arguments) == 2 else ''
    return filename, allow_special, show_queries, page_output, throttle


def parse_source_filename(filename: str) -> str:
    if not filename:
        return ''
    if _has_unquoted_whitespace(filename):
        raise ValueError(INVALID_SOURCE_FILENAME)
    try:
        arguments = shlex.split(filename, posix=not WIN)
    except ValueError as error:
        raise ValueError(f'Invalid source filename: {error}.') from None
    if len(arguments) != 1:
        raise ValueError(INVALID_SOURCE_FILENAME)
    parsed_filename = arguments[0]
    if WIN and len(parsed_filename) >= 2 and parsed_filename[0] == parsed_filename[-1] and parsed_filename[0] in ("'", '"'):
        parsed_filename = parsed_filename[1:-1]
    return parsed_filename


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
