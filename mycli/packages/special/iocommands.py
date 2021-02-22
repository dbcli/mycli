import os
import re
import locale
import logging
import subprocess
import shlex
from io import open
from time import sleep

import click
import pyperclip
import sqlparse

from . import export
from .main import special_command, NO_QUERY, PARSED_QUERY
from .favoritequeries import FavoriteQueries
from .delimitercommand import DelimiterCommand
from .utils import handle_cd_command
from mycli.packages.prompt_utils import confirm_destructive_query

TIMING_ENABLED = False
use_expanded_output = False
PAGER_ENABLED = True
tee_file = None
once_file = None
written_to_once_file = False
pipe_once_process = None
written_to_pipe_once_process = False
delimiter_command = DelimiterCommand()


@export
def set_timing_enabled(val):
    global TIMING_ENABLED
    TIMING_ENABLED = val

@export
def set_pager_enabled(val):
    global PAGER_ENABLED
    PAGER_ENABLED = val


@export
def is_pager_enabled():
    return PAGER_ENABLED

@export
@special_command('pager', '\\P [command]',
                 'Set PAGER. Print the query results via PAGER.',
                 arg_type=PARSED_QUERY, aliases=('\\P', ), case_sensitive=True)
def set_pager(arg, **_):
    if arg:
        os.environ['PAGER'] = arg
        msg = 'PAGER set to %s.' % arg
        set_pager_enabled(True)
    else:
        if 'PAGER' in os.environ:
            msg = 'PAGER set to %s.' % os.environ['PAGER']
        else:
            # This uses click's default per echo_via_pager.
            msg = 'Pager enabled.'
        set_pager_enabled(True)

    return [(None, None, None, msg)]

@export
@special_command('nopager', '\\n', 'Disable pager, print to stdout.',
                 arg_type=NO_QUERY, aliases=('\\n', ), case_sensitive=True)
def disable_pager():
    set_pager_enabled(False)
    return [(None, None, None, 'Pager disabled.')]

@special_command('\\timing', '\\t', 'Toggle timing of commands.', arg_type=NO_QUERY, aliases=('\\t', ), case_sensitive=True)
def toggle_timing():
    global TIMING_ENABLED
    TIMING_ENABLED = not TIMING_ENABLED
    message = "Timing is "
    message += "on." if TIMING_ENABLED else "off."
    return [(None, None, None, message)]

@export
def is_timing_enabled():
    return TIMING_ENABLED

@export
def set_expanded_output(val):
    global use_expanded_output
    use_expanded_output = val

@export
def is_expanded_output():
    return use_expanded_output

_logger = logging.getLogger(__name__)

@export
def editor_command(command):
    """
    Is this an external editor command?
    :param command: string
    """
    # It is possible to have `\e filename` or `SELECT * FROM \e`. So we check
    # for both conditions.
    return command.strip().endswith('\\e') or command.strip().startswith('\\e')

@export
def get_filename(sql):
    if sql.strip().startswith('\\e'):
        command, _, filename = sql.partition(' ')
        return filename.strip() or None


@export
def get_editor_query(sql):
    """Get the query part of an editor command."""
    sql = sql.strip()

    # The reason we can't simply do .strip('\e') is that it strips characters,
    # not a substring. So it'll strip "e" in the end of the sql also!
    # Ex: "select * from style\e" -> "select * from styl".
    pattern = re.compile(r'(^\\e|\\e$)')
    while pattern.search(sql):
        sql = pattern.sub('', sql)

    return sql


@export
def open_external_editor(filename=None, sql=None):
    """Open external editor, wait for the user to type in their query, return
    the query.

    :return: list with one tuple, query as first element.

    """

    message = None
    filename = filename.strip().split(' ', 1)[0] if filename else None

    sql = sql or ''
    MARKER = '# Type your query above this line.\n'

    # Populate the editor buffer with the partial sql (if available) and a
    # placeholder comment.
    query = click.edit(u'{sql}\n\n{marker}'.format(sql=sql, marker=MARKER),
                       filename=filename, extension='.sql')

    if filename:
        try:
            with open(filename) as f:
                query = f.read()
        except IOError:
            message = 'Error reading file: %s.' % filename

    if query is not None:
        query = query.split(MARKER, 1)[0].rstrip('\n')
    else:
        # Don't return None for the caller to deal with.
        # Empty string is ok.
        query = sql

    return (query, message)


@export
def clip_command(command):
    """Is this a clip command?

    :param command: string

    """
    # It is possible to have `\clip` or `SELECT * FROM \clip`. So we check
    # for both conditions.
    return command.strip().endswith('\\clip') or command.strip().startswith('\\clip')


@export
def get_clip_query(sql):
    """Get the query part of a clip command."""
    sql = sql.strip()

    # The reason we can't simply do .strip('\clip') is that it strips characters,
    # not a substring. So it'll strip "c" in the end of the sql also!
    pattern = re.compile(r'(^\\clip|\\clip$)')
    while pattern.search(sql):
        sql = pattern.sub('', sql)

    return sql


@export
def copy_query_to_clipboard(sql=None):
    """Send query to the clipboard."""

    sql = sql or ''
    message = None

    try:
        pyperclip.copy(u'{sql}'.format(sql=sql))
    except RuntimeError as e:
        message = 'Error clipping query: %s.' % e.strerror

    return message


@special_command('\\f', '\\f [name [args..]]', 'List or execute favorite queries.', arg_type=PARSED_QUERY, case_sensitive=True)
def execute_favorite_query(cur, arg, **_):
    """Returns (title, rows, headers, status)"""
    if arg == '':
        for result in list_favorite_queries():
            yield result

    """Parse out favorite name and optional substitution parameters"""
    name, _, arg_str = arg.partition(' ')
    args = shlex.split(arg_str)

    query = FavoriteQueries.instance.get(name)
    if query is None:
        message = "No favorite query: %s" % (name)
        yield (None, None, None, message)
    else:
        query, arg_error = subst_favorite_query_args(query, args)
        if arg_error:
            yield (None, None, None, arg_error)
        else:
            for sql in sqlparse.split(query):
                sql = sql.rstrip(';')
                title = '> %s' % (sql)
                cur.execute(sql)
                if cur.description:
                    headers = [x[0] for x in cur.description]
                    yield (title, cur, headers, None)
                else:
                    yield (title, None, None, None)

def list_favorite_queries():
    """List of all favorite queries.
    Returns (title, rows, headers, status)"""

    headers = ["Name", "Query"]
    rows = [(r, FavoriteQueries.instance.get(r))
            for r in FavoriteQueries.instance.list()]

    if not rows:
        status = '\nNo favorite queries found.' + FavoriteQueries.instance.usage
    else:
        status = ''
    return [('', rows, headers, status)]


def subst_favorite_query_args(query, args):
    """replace positional parameters ($1...$N) in query."""
    for idx, val in enumerate(args):
        subst_var = '$' + str(idx + 1)
        if subst_var not in query:
            return [None, 'query does not have substitution parameter ' + subst_var + ':\n  ' + query]

        query = query.replace(subst_var, val)

    match = re.search(r'\$\d+', query)
    if match:
        return[None, 'missing substitution for ' + match.group(0) + ' in query:\n  ' + query]

    return [query, None]

@special_command('\\fs', '\\fs name query', 'Save a favorite query.')
def save_favorite_query(arg, **_):
    """Save a new favorite query.
    Returns (title, rows, headers, status)"""

    usage = 'Syntax: \\fs name query.\n\n' + FavoriteQueries.instance.usage
    if not arg:
        return [(None, None, None, usage)]

    name, _, query = arg.partition(' ')

    # If either name or query is missing then print the usage and complain.
    if (not name) or (not query):
        return [(None, None, None,
            usage + 'Err: Both name and query are required.')]

    FavoriteQueries.instance.save(name, query)
    return [(None, None, None, "Saved.")]


@special_command('\\fd', '\\fd [name]', 'Delete a favorite query.')
def delete_favorite_query(arg, **_):
    """Delete an existing favorite query."""
    usage = 'Syntax: \\fd name.\n\n' + FavoriteQueries.instance.usage
    if not arg:
        return [(None, None, None, usage)]

    status = FavoriteQueries.instance.delete(arg)

    return [(None, None, None, status)]


@special_command('system', 'system [command]',
                 'Execute a system shell commmand.')
def execute_system_command(arg, **_):
    """Execute a system shell command."""
    usage = "Syntax: system [command].\n"

    if not arg:
        return [(None, None, None, usage)]

    try:
        command = arg.strip()
        if command.startswith('cd'):
            ok, error_message = handle_cd_command(arg)
            if not ok:
                return [(None, None, None, error_message)]
            return [(None, None, None, '')]

        args = arg.split(' ')
        process = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        output, error = process.communicate()
        response = output if not error else error

        # Python 3 returns bytes. This needs to be decoded to a string.
        if isinstance(response, bytes):
            encoding = locale.getpreferredencoding(False)
            response = response.decode(encoding)

        return [(None, None, None, response)]
    except OSError as e:
        return [(None, None, None, 'OSError: %s' % e.strerror)]


def parseargfile(arg):
    if arg.startswith('-o '):
        mode = "w"
        filename = arg[3:]
    else:
        mode = 'a'
        filename = arg

    if not filename:
        raise TypeError('You must provide a filename.')

    return {'file': os.path.expanduser(filename), 'mode': mode}


@special_command('tee', 'tee [-o] filename',
                 'Append all results to an output file (overwrite using -o).')
def set_tee(arg, **_):
    global tee_file

    try:
        tee_file = open(**parseargfile(arg))
    except (IOError, OSError) as e:
        raise OSError("Cannot write to file '{}': {}".format(e.filename, e.strerror))

    return [(None, None, None, "")]

@export
def close_tee():
    global tee_file
    if tee_file:
        tee_file.close()
        tee_file = None


@special_command('notee', 'notee', 'Stop writing results to an output file.')
def no_tee(arg, **_):
    close_tee()
    return [(None, None, None, "")]

@export
def write_tee(output):
    global tee_file
    if tee_file:
        click.echo(output, file=tee_file, nl=False)
        click.echo(u'\n', file=tee_file, nl=False)
        tee_file.flush()


@special_command('\\once', '\\o [-o] filename',
                 'Append next result to an output file (overwrite using -o).',
                 aliases=('\\o', ))
def set_once(arg, **_):
    global once_file, written_to_once_file

    try:
        once_file = open(**parseargfile(arg))
    except (IOError, OSError) as e:
        raise OSError("Cannot write to file '{}': {}".format(
            e.filename, e.strerror))
    written_to_once_file = False

    return [(None, None, None, "")]


@export
def write_once(output):
    global once_file, written_to_once_file
    if output and once_file:
        click.echo(output, file=once_file, nl=False)
        click.echo(u"\n", file=once_file, nl=False)
        once_file.flush()
        written_to_once_file = True


@export
def unset_once_if_written():
    """Unset the once file, if it has been written to."""
    global once_file, written_to_once_file
    if written_to_once_file and once_file:
        once_file.close()
        once_file = None


@special_command('\\pipe_once', '\\| command',
                 'Send next result to a subprocess.',
                 aliases=('\\|', ))
def set_pipe_once(arg, **_):
    global pipe_once_process, written_to_pipe_once_process
    pipe_once_cmd = shlex.split(arg)
    if len(pipe_once_cmd) == 0:
        raise OSError("pipe_once requires a command")
    written_to_pipe_once_process = False
    pipe_once_process = subprocess.Popen(pipe_once_cmd,
                                         stdin=subprocess.PIPE,
                                         stdout=subprocess.PIPE,
                                         stderr=subprocess.PIPE,
                                         bufsize=1,
                                         encoding='UTF-8',
                                         universal_newlines=True)
    return [(None, None, None, "")]


@export
def write_pipe_once(output):
    global pipe_once_process, written_to_pipe_once_process
    if output and pipe_once_process:
        try:
            click.echo(output, file=pipe_once_process.stdin, nl=False)
            click.echo(u"\n", file=pipe_once_process.stdin, nl=False)
        except (IOError, OSError) as e:
            pipe_once_process.terminate()
            raise OSError(
                "Failed writing to pipe_once subprocess: {}".format(e.strerror))
        written_to_pipe_once_process = True


@export
def unset_pipe_once_if_written():
    """Unset the pipe_once cmd, if it has been written to."""
    global pipe_once_process, written_to_pipe_once_process
    if written_to_pipe_once_process:
        (stdout_data, stderr_data) = pipe_once_process.communicate()
        if len(stdout_data) > 0:
            print(stdout_data.rstrip(u"\n"))
        if len(stderr_data) > 0:
            print(stderr_data.rstrip(u"\n"))
        pipe_once_process = None
        written_to_pipe_once_process = False


@special_command(
    'watch',
    'watch [seconds] [-c] query',
    'Executes the query every [seconds] seconds (by default 5).'
)
def watch_query(arg, **kwargs):
    usage = """Syntax: watch [seconds] [-c] query.
    * seconds: The interval at the query will be repeated, in seconds.
               By default 5.
    * -c: Clears the screen between every iteration.
"""
    if not arg:
        yield (None, None, None, usage)
        return
    seconds = 5
    clear_screen = False
    statement = None
    while statement is None:
        arg = arg.strip()
        if not arg:
            # Oops, we parsed all the arguments without finding a statement
            yield (None, None, None, usage)
            return
        (current_arg, _, arg) = arg.partition(' ')
        try:
            seconds = float(current_arg)
            continue
        except ValueError:
            pass
        if current_arg == '-c':
            clear_screen = True
            continue
        statement = '{0!s} {1!s}'.format(current_arg, arg)
    destructive_prompt = confirm_destructive_query(statement)
    if destructive_prompt is False:
        click.secho("Wise choice!")
        return
    elif destructive_prompt is True:
        click.secho("Your call!")
    cur = kwargs['cur']
    sql_list = [
        (sql.rstrip(';'), "> {0!s}".format(sql))
        for sql in sqlparse.split(statement)
    ]
    old_pager_enabled = is_pager_enabled()
    while True:
        if clear_screen:
            click.clear()
        try:
            # Somewhere in the code the pager its activated after every yield,
            # so we disable it in every iteration
            set_pager_enabled(False)
            for (sql, title) in sql_list:
                cur.execute(sql)
                if cur.description:
                    headers = [x[0] for x in cur.description]
                    yield (title, cur, headers, None)
                else:
                    yield (title, None, None, None)
            sleep(seconds)
        except KeyboardInterrupt:
            # This prints the Ctrl-C character in its own line, which prevents
            # to print a line with the cursor positioned behind the prompt
            click.secho("", nl=True)
            return
        finally:
            set_pager_enabled(old_pager_enabled)


@export
@special_command('delimiter', None, 'Change SQL delimiter.')
def set_delimiter(arg, **_):
    return delimiter_command.set(arg)


@export
def get_current_delimiter():
    return delimiter_command.current


@export
def split_queries(input):
    for query in delimiter_command.queries_iter(input):
        yield query
