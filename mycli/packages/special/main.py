from dataclasses import dataclass
from enum import Enum
import logging
import os
from typing import Callable
import webbrowser

from mycli.constants import DOCS_URL, ISSUES_URL
from mycli.packages.sqlresult import SQLResult

try:
    if not os.environ.get('MYCLI_LLM_OFF'):
        import llm  # noqa: F401

        LLM_IMPORTED = True
    else:
        LLM_IMPORTED = False
except ImportError:
    LLM_IMPORTED = False
from pymysql.cursors import Cursor

logger = logging.getLogger(__name__)

COMMANDS = {}
CASE_SENSITIVE_COMMANDS = set()
CASE_INSENSITIVE_COMMANDS = set()


class ArgType(Enum):
    NO_QUERY = 0
    PARSED_QUERY = 1
    RAW_QUERY = 2


@dataclass(frozen=True)
class SpecialCommandAlias:
    command: str
    case_sensitive: bool


@dataclass(frozen=True)
class SpecialCommand:
    handler: Callable
    command: str
    usage: str
    description: str
    arg_type: ArgType
    hidden: bool | None
    case_sensitive: bool | None
    aliases: list[SpecialCommandAlias] | None


class CommandNotFound(Exception):
    pass


class CommandVerbosity(Enum):
    SUCCINCT = "succinct"
    NORMAL = "normal"
    VERBOSE = "verbose"


def parse_special_command(sql: str) -> tuple[str, CommandVerbosity, str]:
    command, _, arg = sql.partition(" ")
    command_verbosity = CommandVerbosity.NORMAL
    if "+" in command:
        command_verbosity = CommandVerbosity.VERBOSE
    elif "-" in command:
        command_verbosity = CommandVerbosity.SUCCINCT
    command = command.strip().strip("+-")
    return (command, command_verbosity, arg.strip())


def special_command(
    command: str,
    usage: str,
    description: str,
    arg_type: ArgType = ArgType.PARSED_QUERY,
    hidden: bool = False,
    case_sensitive: bool = False,
    aliases: list[SpecialCommandAlias] | None = None,
) -> Callable:
    def wrapper(wrapped):
        register_special_command(
            wrapped,
            command,
            usage,
            description,
            arg_type=arg_type,
            hidden=hidden,
            case_sensitive=case_sensitive,
            aliases=aliases,
        )
        return wrapped

    return wrapper


def register_special_command(
    handler: Callable,
    command: str,
    usage: str,
    description: str,
    arg_type: ArgType = ArgType.PARSED_QUERY,
    hidden: bool = False,
    case_sensitive: bool = False,
    aliases: list[SpecialCommandAlias] | None = None,
) -> None:
    cmd = command.lower() if not case_sensitive else command
    COMMANDS[cmd] = SpecialCommand(
        handler,
        command,
        usage,
        description,
        arg_type=arg_type,
        hidden=hidden,
        case_sensitive=case_sensitive,
        aliases=aliases,
    )
    if case_sensitive:
        CASE_SENSITIVE_COMMANDS.add(command)
    else:
        CASE_INSENSITIVE_COMMANDS.add(command.lower())
    aliases = [] if aliases is None else aliases
    for alias in aliases:
        cmd = alias.command.lower() if not alias.case_sensitive else alias.command
        if alias.case_sensitive:
            CASE_SENSITIVE_COMMANDS.add(alias.command)
        else:
            CASE_INSENSITIVE_COMMANDS.add(alias.command.lower())
        COMMANDS[cmd] = SpecialCommand(
            handler,
            command,
            usage,
            description,
            arg_type=arg_type,
            case_sensitive=alias.case_sensitive,
            hidden=True,
            aliases=None,
        )


def execute(cur: Cursor, sql: str) -> list[SQLResult]:
    """Execute a special command and return the results. If the special command
    is not supported a CommandNotFound will be raised.
    """
    command, command_verbosity, arg = parse_special_command(sql)

    if (command not in CASE_SENSITIVE_COMMANDS) and (command.lower() not in CASE_INSENSITIVE_COMMANDS):
        raise CommandNotFound(f'Command not found: {command}')

    try:
        special_cmd = COMMANDS[command]
    except KeyError as exc:
        special_cmd = COMMANDS[command.lower()]
        if special_cmd.case_sensitive:
            raise CommandNotFound(f'Command not found: {command}') from exc

    # "help <SQL KEYWORD> is a special case. We want built-in help, not
    # mycli help here.
    if command.lower() == "help" and arg:
        return show_keyword_help(cur=cur, arg=arg)

    if special_cmd.arg_type == ArgType.NO_QUERY:
        return special_cmd.handler()
    elif special_cmd.arg_type == ArgType.PARSED_QUERY:
        return special_cmd.handler(cur=cur, arg=arg, command_verbosity=(command_verbosity == CommandVerbosity.VERBOSE))
    elif special_cmd.arg_type == ArgType.RAW_QUERY:
        return special_cmd.handler(cur=cur, query=sql)

    raise CommandNotFound(f"Command type not found: {command}")


@special_command(
    "help",
    "help [term]",
    "Show this table, or search for help on a term.",
    arg_type=ArgType.NO_QUERY,
    aliases=[SpecialCommandAlias("\\?", case_sensitive=False), SpecialCommandAlias("?", case_sensitive=False)],
)
def show_help(*_args) -> list[SQLResult]:
    header = ["Command", "Shortcut", "Usage", "Description"]
    result = []

    for _, value in sorted(COMMANDS.items(), key=lambda x: str.casefold(x[0])):
        if value.hidden:
            continue
        if value.aliases:
            shortcut = value.aliases[0].command
        else:
            shortcut = None
        result.append((value.command, shortcut, value.usage, value.description))
    return [SQLResult(header=header, rows=result, postamble=f'Docs index — {DOCS_URL}')]


def _show_special_help(keyword: str) -> list[SQLResult]:
    header = ['name', 'description', 'example']
    command = COMMANDS[keyword]
    description = '\n'.join([command.usage or '', command.description])
    rows = [(keyword, description, '')]
    return [SQLResult(header=header, rows=rows)]


def _show_mysql_help(cur: Cursor, keyword: str) -> list[SQLResult]:
    """
    Call the built-in "show <keyword>", to display help for an SQL keyword.
    :param cur: cursor
    :param arg: string
    :return: list
    """
    query = 'help %s'
    logger.debug(query)
    cur.execute(query, keyword)
    if cur.description and cur.rowcount > 0:
        header = [x[0] for x in cur.description]
        return [SQLResult(header=header, rows=cur)]
    logger.debug(query)
    cur.execute(query, (f'%{keyword}%',))
    if cur.description and cur.rowcount > 0:
        header = [x[0] for x in cur.description]
        return [SQLResult(preamble='Similar terms:', header=header, rows=cur)]
    else:
        return [SQLResult(status=f'No help found for "{keyword}".')]


def show_keyword_help(cur: Cursor, arg: str) -> list[SQLResult]:
    keyword = arg.strip().strip('"').strip("'").rstrip('+-')

    if keyword in CASE_SENSITIVE_COMMANDS:
        return _show_special_help(keyword)
    elif keyword.lower() in CASE_INSENSITIVE_COMMANDS:
        return _show_special_help(keyword.lower())

    return _show_mysql_help(cur, keyword)


@special_command('\\bug', '\\bug', 'File a bug on GitHub.', arg_type=ArgType.NO_QUERY)
def file_bug(*_args) -> list[SQLResult]:
    webbrowser.open_new_tab(ISSUES_URL)
    return [SQLResult(status=f'{ISSUES_URL} — press "New Issue"')]


@special_command(
    "exit",
    "exit",
    "Exit.",
    arg_type=ArgType.NO_QUERY,
    aliases=[SpecialCommandAlias("\\q", case_sensitive=False)],
)
@special_command(
    "quit",
    "quit",
    "Quit.",
    arg_type=ArgType.NO_QUERY,
    aliases=[SpecialCommandAlias("\\q", case_sensitive=False)],
)
def quit_(*_args):
    raise EOFError


@special_command(
    "\\edit",
    "<query>\\edit | \\edit <filename>",
    "Edit query with editor (uses $VISUAL or $EDITOR).",
    arg_type=ArgType.NO_QUERY,
    case_sensitive=True,
    aliases=[SpecialCommandAlias("\\e", case_sensitive=True)],
)
@special_command(
    "\\clip",
    "<query>\\clip",
    "Copy query to the system clipboard.",
    arg_type=ArgType.NO_QUERY,
    case_sensitive=True,
)
@special_command(
    "\\G",
    "<query>\\G",
    "Display query results vertically.",
    arg_type=ArgType.NO_QUERY,
    case_sensitive=True,
)
@special_command(
    "\\g",
    "<query>\\g",
    "Display query results (mnemonic: go).",
    arg_type=ArgType.NO_QUERY,
    case_sensitive=True,
)
def stub():
    raise NotImplementedError


if LLM_IMPORTED:

    @special_command(
        "\\llm",
        "\\llm [arguments]",
        "Interrogate an LLM.  See \"\\llm help\".",
        arg_type=ArgType.RAW_QUERY,
        case_sensitive=True,
        aliases=[SpecialCommandAlias("\\ai", case_sensitive=True)],
    )
    def llm_stub():
        raise NotImplementedError
