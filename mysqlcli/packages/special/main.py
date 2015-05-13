import sys
from . import export
from .iocommands import toggle_timing, stub
from .dbcommands import change_db

@export
def show_help(*args):  # All the parameters are ignored.
    headers = ['Command', 'Shortcut', 'Description']
    result = []

    for command, value in sorted(COMMANDS.items()):
        if value[1]:
            result.append(value[1])
    return [(None, result, headers, None)]

HIDDEN_COMMANDS = {
            }

COMMANDS = {
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

@export
def parse_special_command(sql):
    command, _, arg = sql.partition(' ')
    return (command, arg.strip())

@export
def execute(cur, sql, db_obj=None):
    """Execute a special command and return the results. If the special command
    is not supported a KeyError will be raised.
    """
    command, arg = parse_special_command(sql)

    # Look up the command in the case-sensitive dict, if it's not there look in
    # non-case-sensitive dict. If not there either, throw a KeyError exception.
    try:
        command_executor = COMMANDS[command.lower()][0]
    except KeyError:
        command_executor = HIDDEN_COMMANDS[command.lower()][0]

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
    for rows, headers, status in execute(cur, '\\l'):
        print((rows, headers, status))
