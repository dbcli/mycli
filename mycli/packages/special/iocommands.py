from __future__ import annotations

import locale
import logging
import os
import re
import shlex
import subprocess
from time import sleep
from typing import Any, Generator

import click
from configobj import ConfigObj
from pymysql.cursors import Cursor
import pyperclip
import sqlparse

from mycli.compat import WIN
from mycli.packages.prompt_utils import confirm_destructive_query
from mycli.packages.special.delimitercommand import DelimiterCommand
from mycli.packages.special.favoritequeries import FavoriteQueries
from mycli.packages.special.main import COMMANDS as SPECIAL_COMMANDS
from mycli.packages.special.main import ArgType, special_command
from mycli.packages.special.main import execute as special_execute
from mycli.packages.special.utils import handle_cd_command
from mycli.packages.sqlresult import SQLResult

sqlparse.engine.grouping.MAX_GROUPING_DEPTH = None  # type: ignore[assignment]
sqlparse.engine.grouping.MAX_GROUPING_TOKENS = None  # type: ignore[assignment]

TIMING_ENABLED = False
use_expanded_output = False
force_horizontal_output = False
PAGER_ENABLED = True
SHOW_FAVORITE_QUERY = True
tee_file = None
once_file = None
written_to_once_file = False
PIPE_ONCE: dict[str, Any] = {
    'process': None,
    'stdin': [],
    'stdout_file': None,
    'stdout_mode': None,
}
delimiter_command = DelimiterCommand()
favoritequeries = FavoriteQueries(ConfigObj())
DESTRUCTIVE_KEYWORDS: list[str] = []


def set_favorite_queries(config):
    global favoritequeries
    favoritequeries = FavoriteQueries(config)


def set_timing_enabled(val: bool) -> None:
    global TIMING_ENABLED
    TIMING_ENABLED = val


def set_pager_enabled(val: bool) -> None:
    global PAGER_ENABLED
    PAGER_ENABLED = val


def is_pager_enabled() -> bool:
    return PAGER_ENABLED


def set_show_favorite_query(val: bool) -> None:
    global SHOW_FAVORITE_QUERY
    SHOW_FAVORITE_QUERY = val


def is_show_favorite_query() -> bool:
    return SHOW_FAVORITE_QUERY


def set_destructive_keywords(val: list[str]) -> None:
    global DESTRUCTIVE_KEYWORDS
    DESTRUCTIVE_KEYWORDS = val


@special_command(
    "pager",
    "\\P [command]",
    "Set PAGER. Print the query results via PAGER.",
    arg_type=ArgType.PARSED_QUERY,
    aliases=["\\P"],
    case_sensitive=True,
)
def set_pager(arg: str, **_) -> list[SQLResult]:
    if arg:
        os.environ["PAGER"] = arg
        msg = f"PAGER set to {arg}."
        set_pager_enabled(True)
    else:
        if "PAGER" in os.environ:
            msg = f"PAGER set to {os.environ['PAGER']}."
        else:
            # This uses click's default per echo_via_pager.
            msg = "Pager enabled."
        set_pager_enabled(True)

    return [SQLResult(status=msg)]


@special_command("nopager", "\\n", "Disable pager, print to stdout.", arg_type=ArgType.NO_QUERY, aliases=["\\n"], case_sensitive=True)
def disable_pager() -> list[SQLResult]:
    set_pager_enabled(False)
    return [SQLResult(status="Pager disabled.")]


@special_command("\\timing", "\\t", "Toggle timing of commands.", arg_type=ArgType.NO_QUERY, aliases=["\\t"], case_sensitive=True)
def toggle_timing() -> list[SQLResult]:
    global TIMING_ENABLED
    TIMING_ENABLED = not TIMING_ENABLED
    message = "Timing is "
    message += "on." if TIMING_ENABLED else "off."
    return [SQLResult(status=message)]


def is_timing_enabled() -> bool:
    return TIMING_ENABLED


def set_expanded_output(val: bool) -> None:
    global use_expanded_output
    use_expanded_output = val


def is_expanded_output() -> bool:
    return use_expanded_output


def set_forced_horizontal_output(val: bool) -> None:
    global force_horizontal_output
    force_horizontal_output = val


def forced_horizontal() -> bool:
    return force_horizontal_output


_logger = logging.getLogger(__name__)


def editor_command(command: str) -> bool:
    """
    Is this an external editor command?
    :param command: string
    """
    # It is possible to have `\e filename` or `SELECT * FROM \e`. So we check
    # for both conditions.
    return command.strip().endswith("\\e") or command.strip().startswith("\\e")


def get_filename(sql: str) -> str | None:
    if sql.strip().startswith("\\e"):
        command, _, filename = sql.partition(" ")
        return filename.strip() or None
    else:
        return None


def get_editor_query(sql: str) -> str:
    """Get the query part of an editor command."""
    sql = sql.strip()

    # The reason we can't simply do .strip('\e') is that it strips characters,
    # not a substring. So it'll strip "e" in the end of the sql also!
    # Ex: "select * from style\e" -> "select * from styl".
    pattern = re.compile(r"(^\\e|\\e$)")
    while pattern.search(sql):
        sql = pattern.sub("", sql)

    return sql


def open_external_editor(filename: str | None = None, sql: str | None = None) -> tuple[str, str | None]:
    """Open external editor, wait for the user to type in their query, return
    the query.
    """

    filename = filename.strip().split(" ", 1)[0] if filename else None
    sql = sql or ""
    MARKER = "# Type your query above this line.\n"

    if filename:
        query = ''
        message = None
        click.edit(filename=filename)
        try:
            with open(filename, 'r') as f:
                query = f.read()
        except IOError:
            message = f'Error reading file: {filename}'
        return (query, message)

    # Populate the editor buffer with the partial sql (if available) and a
    # placeholder comment.
    query = click.edit(f"{sql}\n\n{MARKER}", extension=".sql") or ''

    if query:
        query = query.split(MARKER, 1)[0].rstrip("\n")
    else:
        # Don't return None for the caller to deal with.
        # Empty string is ok.
        query = sql

    return (query, None)


def clip_command(command: str) -> bool:
    """Is this a clip command?

    :param command: string

    """
    # It is possible to have `\clip` or `SELECT * FROM \clip`. So we check
    # for both conditions.
    return command.strip().endswith("\\clip") or command.strip().startswith("\\clip")


def get_clip_query(sql: str) -> str:
    """Get the query part of a clip command."""
    sql = sql.strip()

    # The reason we can't simply do .strip('\clip') is that it strips characters,
    # not a substring. So it'll strip "c" in the end of the sql also!
    pattern = re.compile(r"(^\\clip|\\clip$)")
    while pattern.search(sql):
        sql = pattern.sub("", sql)

    return sql


def copy_query_to_clipboard(sql: str | None = None) -> str | None:
    """Send query to the clipboard."""

    sql = sql or ""
    message = None

    try:
        pyperclip.copy(f"{sql}")
    except RuntimeError as e:
        message = f"Error clipping query: {e}."

    return message


def set_redirect(command_part: str | None, file_operator_part: str | None, file_part: str | None) -> list[tuple]:
    if command_part:
        if file_part:
            PIPE_ONCE['stdout_file'] = file_part
            PIPE_ONCE['stdout_mode'] = 'w' if file_operator_part == '>' else 'a'
        return set_pipe_once(command_part)
    elif file_operator_part == '>':
        return set_once(f'-o {file_part}')
    else:
        return set_once(file_part)


@special_command("\\f", "\\f [name [args..]]", "List or execute favorite queries.", arg_type=ArgType.PARSED_QUERY, case_sensitive=True)
def execute_favorite_query(cur: Cursor, arg: str, **_) -> Generator[SQLResult, None, None]:
    """Returns (title, rows, headers, status)"""
    if arg == "":
        for result in list_favorite_queries():
            yield result

    # Parse out favorite name and optional substitution parameters
    name, _separator, arg_str = arg.partition(" ")
    args = shlex.split(arg_str)

    query = FavoriteQueries.instance.get(name)
    if query is None:
        message = f"No favorite query: {name}"
        yield SQLResult(status=message)
    else:
        query, arg_error = subst_favorite_query_args(query, args)
        if query is None:
            yield SQLResult(status=arg_error)
        else:
            for sql in sqlparse.split(query):
                sql = sql.rstrip(";")
                title = f"> {sql}" if is_show_favorite_query() else None
                is_special = False
                for special in SPECIAL_COMMANDS:
                    if sql.lower().startswith(special.lower()):
                        is_special = True
                        break
                if is_special:
                    for result in special_execute(cur, sql):
                        result.title = title
                        # special_execute() already returns a SQLResult
                        yield result
                else:
                    cur.execute(sql)
                    if cur.description:
                        headers = [x[0] for x in cur.description]
                        yield SQLResult(title=title, results=cur, headers=headers)
                    else:
                        yield SQLResult(title=title)


def list_favorite_queries() -> list[SQLResult]:
    """List of all favorite queries.
    Returns (title, rows, headers, status)"""

    headers = ["Name", "Query"]
    rows = [(r, FavoriteQueries.instance.get(r)) for r in FavoriteQueries.instance.list()]

    if not rows:
        status = "\nNo favorite queries found." + FavoriteQueries.instance.usage
    else:
        status = ""
    return [SQLResult(title="", results=rows, headers=headers, status=status)]


def subst_favorite_query_args(query: str, args: list[str]) -> list[str | None]:
    """replace positional parameters ($1...$N) in query."""
    for idx, val in enumerate(args):
        subst_var = "$" + str(idx + 1)
        if subst_var not in query:
            return [None, "query does not have substitution parameter " + subst_var + ":\n  " + query]

        query = query.replace(subst_var, val)

    match = re.search(r"\$\d+", query)
    if match:
        return [None, "missing substitution for " + match.group(0) + " in query:\n  " + query]

    return [query, None]


@special_command("\\fs", "\\fs name query", "Save a favorite query.")
def save_favorite_query(arg: str, **_) -> list[SQLResult]:
    """Save a new favorite query.
    Returns (title, rows, headers, status)"""

    usage = "Syntax: \\fs name query.\n\n" + FavoriteQueries.instance.usage
    if not arg:
        return [SQLResult(status=usage)]

    name, _separator, query = arg.partition(" ")

    # If either name or query is missing then print the usage and complain.
    if (not name) or (not query):
        return [SQLResult(status=f"{usage} Err: Both name and query are required.")]

    FavoriteQueries.instance.save(name, query)
    return [SQLResult(status="Saved.")]


@special_command("\\fd", "\\fd [name]", "Delete a favorite query.")
def delete_favorite_query(arg: str, **_) -> list[SQLResult]:
    """Delete an existing favorite query."""
    usage = "Syntax: \\fd name.\n\n" + FavoriteQueries.instance.usage
    if not arg:
        return [SQLResult(status=usage)]

    status = FavoriteQueries.instance.delete(arg)

    return [SQLResult(status=status)]


@special_command("system", "system [command]", "Execute a system shell commmand.")
def execute_system_command(arg: str, **_) -> list[SQLResult]:
    """Execute a system shell command."""
    usage = "Syntax: system [command].\n"

    if not arg:
        return [SQLResult(status=usage)]

    try:
        command = arg.strip()
        if command.startswith("cd"):
            ok, error_message = handle_cd_command(arg)
            if not ok:
                return [SQLResult(status=error_message)]
            return [SQLResult(status="")]

        args = arg.split(" ")
        process = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        output, error = process.communicate()
        response = output if not error else error

        encoding = locale.getpreferredencoding(False)
        response_str = response.decode(encoding)

        return [SQLResult(status=response_str)]
    except OSError as e:
        return [SQLResult(status=f"OSError: {e.strerror}")]


def parseargfile(arg: str) -> tuple[str, str]:
    if arg.startswith("-o "):
        mode = "w"
        filename = arg[3:]
    else:
        mode = "a"
        filename = arg

    if not filename:
        raise TypeError("You must provide a filename.")

    return (os.path.expanduser(filename), mode)


@special_command("tee", "tee [-o] filename", "Append all results to an output file (overwrite using -o).")
def set_tee(arg: str, **_) -> list[SQLResult]:
    global tee_file

    try:
        tee_file = open(*parseargfile(arg))
    except (IOError, OSError) as e:
        raise OSError(f"Cannot write to file '{e.filename}': {e.strerror}") from e

    return [SQLResult(status="")]


def close_tee() -> None:
    global tee_file
    if tee_file:
        tee_file.close()
        tee_file = None


@special_command("notee", "notee", "Stop writing results to an output file.")
def no_tee(arg: str, **_) -> list[SQLResult]:
    close_tee()
    return [SQLResult(status="")]


def write_tee(output: str) -> None:
    global tee_file
    if tee_file:
        click.echo(output, file=tee_file, nl=False)
        click.echo("\n", file=tee_file, nl=False)
        tee_file.flush()


@special_command("\\once", "\\o [-o] filename", "Append next result to an output file (overwrite using -o).", aliases=["\\o"])
def set_once(arg: str, **_) -> list[SQLResult]:
    global once_file, written_to_once_file

    try:
        once_file = open(*parseargfile(arg))
    except (IOError, OSError) as e:
        raise OSError(f"Cannot write to file '{e.filename}': {e.strerror}") from e
    written_to_once_file = False

    return [SQLResult(status="")]


def is_redirected() -> bool:
    return bool(once_file or PIPE_ONCE['process'])


def write_once(output: str) -> None:
    global once_file, written_to_once_file
    if output and once_file:
        click.echo(output, file=once_file, nl=False)
        click.echo("\n", file=once_file, nl=False)
        once_file.flush()
        written_to_once_file = True


def unset_once_if_written(post_redirect_command: str) -> None:
    """Unset the once file, if it has been written to."""
    global once_file, written_to_once_file
    if written_to_once_file and once_file:
        once_filename = once_file.name
        once_file.close()
        once_file = None
        _run_post_redirect_hook(post_redirect_command, once_filename)


def _run_post_redirect_hook(post_redirect_command: str, filename: str) -> None:
    if not post_redirect_command:
        return
    post_cmd = post_redirect_command.format(shlex.quote(filename))
    try:
        subprocess.run(
            post_cmd,
            shell=True,
            check=True,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except Exception as e:
        raise OSError(f"Redirect post hook failed: {e}") from e


@special_command("\\pipe_once", "\\| command", "Send next result to a subprocess.", aliases=["\\|"])
def set_pipe_once(arg: str, **_) -> list[SQLResult]:
    if not arg:
        raise OSError("pipe_once requires a command")
    if WIN:
        # best effort, no chaining
        pipe_once_cmd = shlex.split(arg)
    else:
        # to support chaining
        pipe_once_cmd = ['sh', '-c', arg]
    PIPE_ONCE['stdin'] = []
    PIPE_ONCE['process'] = subprocess.Popen(
        pipe_once_cmd,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        encoding="UTF-8",
        universal_newlines=True,
    )
    return [SQLResult(status="")]


def write_pipe_once(line: str) -> None:
    if line and PIPE_ONCE['process']:
        PIPE_ONCE['stdin'].append(line)


def flush_pipe_once_if_written(post_redirect_command: str) -> None:
    """Flush the pipe_once cmd, if lines have been written."""
    if not PIPE_ONCE['process']:
        return
    if not PIPE_ONCE['stdin']:
        return
    try:
        (stdout_data, stderr_data) = PIPE_ONCE['process'].communicate(input='\n'.join(PIPE_ONCE['stdin']) + '\n', timeout=60)
    except subprocess.TimeoutExpired:
        PIPE_ONCE['process'].kill()
        (stdout_data, stderr_data) = PIPE_ONCE['process'].communicate()
    if stdout_data:
        if PIPE_ONCE['stdout_file']:
            with open(PIPE_ONCE['stdout_file'], PIPE_ONCE['stdout_mode']) as f:
                print(stdout_data, file=f)
            _run_post_redirect_hook(post_redirect_command, PIPE_ONCE['stdout_file'])
        else:
            click.secho(stdout_data.rstrip('\n'))
    if stderr_data:
        click.secho(stderr_data.rstrip('\n'), err=True, fg='red')
    if returncode := PIPE_ONCE['process'].returncode:
        PIPE_ONCE['process'] = None
        PIPE_ONCE['stdin'] = []
        PIPE_ONCE['stdout_file'] = None
        PIPE_ONCE['stdout_mode'] = None
        raise OSError(f'process exited with nonzero code {returncode}')
    PIPE_ONCE['process'] = None
    PIPE_ONCE['stdin'] = []
    PIPE_ONCE['stdout_file'] = None
    PIPE_ONCE['stdout_mode'] = None


@special_command("watch", "watch [seconds] [-c] query", "Executes the query every [seconds] seconds (by default 5).")
def watch_query(arg: str, **kwargs) -> Generator[SQLResult, None, None]:
    usage = """Syntax: watch [seconds] [-c] query.
    * seconds: The interval at the query will be repeated, in seconds.
               By default 5.
    * -c: Clears the screen between every iteration.
"""
    if not arg:
        yield SQLResult(status=usage)
        return
    seconds = 5.0
    clear_screen = False
    statement = None
    while statement is None:
        arg = arg.strip()
        if not arg:
            # Oops, we parsed all the arguments without finding a statement
            yield SQLResult(status=usage)
            return
        (left_arg, _, right_arg) = arg.partition(" ")
        arg = right_arg
        try:
            seconds = float(left_arg)
            continue
        except ValueError:
            pass
        if left_arg == "-c":
            clear_screen = True
            continue
        statement = f"{left_arg} {arg}"
    destructive_prompt = confirm_destructive_query(DESTRUCTIVE_KEYWORDS, statement)
    if destructive_prompt is False:
        click.secho("Wise choice!")
        return
    elif destructive_prompt is True:
        click.secho("Your call!")
    cur = kwargs["cur"]
    sql_list = [(sql.rstrip(";"), f"> {sql}") for sql in sqlparse.split(statement)]
    old_pager_enabled = is_pager_enabled()
    while True:
        if clear_screen:
            click.clear()
        try:
            # Somewhere in the code the pager its activated after every yield,
            # so we disable it in every iteration
            set_pager_enabled(False)
            for sql, title in sql_list:
                cur.execute(sql)
                command: dict[str, str | float] = {
                    "name": "watch",
                    "seconds": seconds,
                }
                if cur.description:
                    headers = [x[0] for x in cur.description]
                    yield SQLResult(title=title, results=cur, headers=headers, command=command)
                else:
                    yield SQLResult(title=title, command=command)
            sleep(seconds)
        except KeyboardInterrupt:
            # This prints the Ctrl-C character in its own line, which prevents
            # to print a line with the cursor positioned behind the prompt
            click.secho("", nl=True)
            return
        finally:
            set_pager_enabled(old_pager_enabled)


@special_command("delimiter", None, "Change SQL delimiter.")
def set_delimiter(arg: str, **_) -> list[SQLResult]:
    return delimiter_command.set(arg)


def get_current_delimiter() -> str:
    return delimiter_command.current


def split_queries(input_str: str) -> Generator[str, None, None]:
    for query in delimiter_command.queries_iter(input_str):
        yield query
