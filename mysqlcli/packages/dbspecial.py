from __future__ import print_function
import sys
import logging
from collections import namedtuple
from .tabulate import tabulate

TableInfo = namedtuple("TableInfo", ['checks', 'relkind', 'hasindex',
'hasrules', 'hastriggers', 'hasoids', 'tablespace', 'reloptions', 'reloftype',
'relpersistence'])


log = logging.getLogger(__name__)

use_expanded_output = False

def set_expanded_output(val):
    global use_expanded_output
    use_expanded_output = val

def is_expanded_output():
    return use_expanded_output

TIMING_ENABLED = False

def parse_special_command(sql):
    command, _, arg = sql.partition(' ')
    return (command, arg.strip())

def sql_name_pattern(pattern):
    """
    Takes a wildcard-pattern and converts to an appropriate SQL pattern to be
    used in a WHERE clause.

    Returns: schema_pattern, table_pattern

    >>> sql_name_pattern('foo*."b""$ar*"')
    ('^(foo.*)$', '^(b"\\\\$ar\\\\*)$')
    """

    inquotes = False
    relname = ''
    schema = None
    pattern_len = len(pattern)
    i = 0

    while i < pattern_len:
        c = pattern[i]
        if c == '"':
            if inquotes and i + 1 < pattern_len and pattern[i + 1] == '"':
                relname += '"'
                i += 1
            else:
                inquotes = not inquotes
        elif not inquotes and c.isupper():
            relname += c.lower()
        elif not inquotes and c == '*':
            relname += '.*'
        elif not inquotes and c == '?':
            relname += '.'
        elif not inquotes and c == '.':
            # Found schema/name separator, move current pattern to schema
            schema = relname
            relname = ''
        else:
            # Dollar is always quoted, whether inside quotes or not.
            if c == '$' or inquotes and c in '|*+?()[]{}.^\\':
                relname += '\\'
            relname += c
        i += 1

    if relname:
        relname = '^(' + relname + ')$'

    if schema:
        schema = '^(' + schema + ')$'

    return schema, relname

def show_help(*args):  # All the parameters are ignored.
    headers = ['Command', 'Shortcut', 'Description']
    result = []

    for command, value in sorted(CASE_SENSITIVE_COMMANDS.items()):
        if value[1]:
            result.append(value[1])
    return [(None, result, headers, None)]

def quit(*args):
    raise NotImplementedError

def expanded_output(*args):
    global use_expanded_output
    use_expanded_output = not use_expanded_output
    message = u"Expanded display is "
    message += u"on." if use_expanded_output else u"off."
    return [(None, None, None, message)]

def stub(*args):
    raise NotImplementedError

def toggle_timing(*args):
    global TIMING_ENABLED
    TIMING_ENABLED = not TIMING_ENABLED
    message = "Timing is "
    message += "on." if TIMING_ENABLED else "off."
    return [(None, None, None, message)]

def change_db(cur, arg, db_obj):
    if arg is None:
        db_obj.connect()
    else:
        db_obj.connect(database=arg)

    yield (None, None, None, 'You are now connected to database "%s" as '
            'user "%s"' % (db_obj.dbname, db_obj.user))


NON_CASE_SENSITIVE_COMMANDS = {
            }

CASE_SENSITIVE_COMMANDS = {
            '\\?': (show_help, ['\\?', '(\\?)', 'Show this help.']),
            'help': (show_help, ['help', '(\\?)', 'Show this help.']),
            '?': (show_help, ['?', '(\\?)', 'Show this help.']),
            'connect': (change_db, ['connect', '(\\r)', 'Reconnect to the server. Optional arguments are db and host.']),
            '\\G': (stub, ['\\G', '(\\G)', 'Display results vertically.']),
            'exit': (stub, ['exit', '(\\q)', 'Exit.']),
            'quit': (stub, ['quit', '(\\q)', 'Quit.']),
            '\\u': (change_db, ['\\u', '(\\u)', 'Use another database.']),
            '\\l': ('''SHOW DATABASES;''', ['\\l', '(\\l)', 'List databases.']),
            '\\timing': (toggle_timing, ['\\timing', '(\\t)', 'Toggle timing of commands.']),
            }

def execute(cur, sql, db_obj=None):
    """Execute a special command and return the results. If the special command
    is not supported a KeyError will be raised.
    """
    command, arg = parse_special_command(sql)

    # Look up the command in the case-sensitive dict, if it's not there look in
    # non-case-sensitive dict. If not there either, throw a KeyError exception.
    global CASE_SENSITIVE_COMMANDS
    global NON_CASE_SENSITIVE_COMMANDS
    try:
        command_executor = CASE_SENSITIVE_COMMANDS[command][0]
    except KeyError:
        command_executor = NON_CASE_SENSITIVE_COMMANDS[command.lower()][0]

    # If the command executor is a function, then call the function with the
    # args. If it's a string, then assume it's an SQL command and run it.
    if callable(command_executor):
        return command_executor(cur, arg, db_obj)
    elif isinstance(command_executor, str):
        cur.execute(command_executor)
        if cur.description:
            headers = [x[0] for x in cur.description]
            return [(None, cur, headers, None)]
        else:
            return [(None, None, None, None)]

if __name__ == '__main__':
    import pymysql
    con = pymysql.connect(database='misago_testforum')
    cur = con.cursor()
    table = sys.argv[1]
    for rows, headers, status in describe_table_details(cur, table, False):
        print(tabulate(rows, headers, tablefmt='psql'))
        print(status)
