from collections import namedtuple
from enum import Enum
import logging
import os
from typing import Callable

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

SpecialCommand = namedtuple(
    "SpecialCommand",
    [
        "handler",
        "command",
        "shortcut",
        "description",
        "arg_type",
        "hidden",
        "case_sensitive",
    ],
)


class ArgType(Enum):
    NO_QUERY = 0
    PARSED_QUERY = 1
    RAW_QUERY = 2


class CommandNotFound(Exception):
    pass


class Verbosity(Enum):
    SUCCINCT = "succinct"
    NORMAL = "normal"
    VERBOSE = "verbose"


def parse_special_command(sql: str) -> tuple[str, Verbosity, str]:
    command, _, arg = sql.partition(" ")
    verbosity = Verbosity.NORMAL
    if "+" in command:
        verbosity = Verbosity.VERBOSE
    elif "-" in command:
        verbosity = Verbosity.SUCCINCT
    command = command.strip().strip("+-")
    return (command, verbosity, arg.strip())


def special_command(
    command: str,
    shortcut: str | None,
    description: str,
    arg_type: ArgType = ArgType.PARSED_QUERY,
    hidden: bool = False,
    case_sensitive: bool = False,
    aliases: list[str] | None = None,
) -> Callable:
    def wrapper(wrapped):
        register_special_command(
            wrapped,
            command,
            shortcut,
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
    shortcut: str | None,
    description: str,
    arg_type: ArgType = ArgType.PARSED_QUERY,
    hidden: bool = False,
    case_sensitive: bool = False,
    aliases: list[str] | None = None,
) -> None:
    cmd = command.lower() if not case_sensitive else command
    COMMANDS[cmd] = SpecialCommand(
        handler,
        command,
        shortcut,
        description,
        arg_type=arg_type,
        hidden=hidden,
        case_sensitive=case_sensitive,
    )
    aliases = [] if aliases is None else aliases
    for alias in aliases:
        cmd = alias.lower() if not case_sensitive else alias
        COMMANDS[cmd] = SpecialCommand(
            handler,
            command,
            shortcut,
            description,
            arg_type=arg_type,
            case_sensitive=case_sensitive,
            hidden=True,
        )


def execute(cur: Cursor, sql: str) -> list[tuple]:
    """Execute a special command and return the results. If the special command
    is not supported a CommandNotFound will be raised.
    """
    command, verbosity, arg = parse_special_command(sql)

    if (command not in COMMANDS) and (command.lower() not in COMMANDS):
        raise CommandNotFound()

    try:
        special_cmd = COMMANDS[command]
    except KeyError as exc:
        special_cmd = COMMANDS[command.lower()]
        if special_cmd.case_sensitive:
            raise CommandNotFound(f'Command not found: {command}') from exc

    # "help <SQL KEYWORD> is a special case. We want built-in help, not
    # mycli help here.
    if command == "help" and arg:
        return show_keyword_help(cur=cur, arg=arg)

    if special_cmd.arg_type == ArgType.NO_QUERY:
        return special_cmd.handler()
    elif special_cmd.arg_type == ArgType.PARSED_QUERY:
        return special_cmd.handler(cur=cur, arg=arg, verbose=(verbosity == Verbosity.VERBOSE))
    elif special_cmd.arg_type == ArgType.RAW_QUERY:
        return special_cmd.handler(cur=cur, query=sql)

    raise CommandNotFound(f"Command type not found: {command}")


@special_command("help", "\\?", "Show this help.", arg_type=ArgType.NO_QUERY, aliases=["\\?", "?"])
def show_help(*_args) -> list[tuple]:
    headers = ["Command", "Shortcut", "Description"]
    result = []

    for _, value in sorted(COMMANDS.items()):
        if not value.hidden:
            result.append((value.command, value.shortcut, value.description))
    return [(None, result, headers, None)]


def show_keyword_help(cur: Cursor, arg: str) -> list[tuple]:
    """
    Call the built-in "show <command>", to display help for an SQL keyword.
    :param cur: cursor
    :param arg: string
    :return: list
    """
    keyword = arg.strip('"').strip("'")
    query = f"help '{keyword}'"
    logger.debug(query)
    cur.execute(query)
    if cur.description and cur.rowcount > 0:
        headers = [x[0] for x in cur.description]
        return [(None, cur, headers, "")]
    else:
        return [(None, None, None, f'No help found for {keyword}.')]


@special_command("exit", "\\q", "Exit.", arg_type=ArgType.NO_QUERY, aliases=["\\q"])
@special_command("quit", "\\q", "Quit.", arg_type=ArgType.NO_QUERY)
def quit_(*_args):
    raise EOFError


@special_command("\\e", "\\e", "Edit command with editor (uses $EDITOR).", arg_type=ArgType.NO_QUERY, case_sensitive=True)
@special_command("\\clip", "\\clip", "Copy query to the system clipboard.", arg_type=ArgType.NO_QUERY, case_sensitive=True)
@special_command("\\G", "\\G", "Display current query results vertically.", arg_type=ArgType.NO_QUERY, case_sensitive=True)
def stub():
    raise NotImplementedError


if LLM_IMPORTED:

    @special_command("\\llm", "\\ai", "Interrogate LLM.", arg_type=ArgType.RAW_QUERY, case_sensitive=True)
    def llm_stub():
        raise NotImplementedError
