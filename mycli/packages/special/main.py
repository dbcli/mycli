import logging
from collections import namedtuple

from . import export

log = logging.getLogger(__name__)

NO_QUERY = 0
PARSED_QUERY = 1
RAW_QUERY = 2

SpecialCommand = namedtuple('SpecialCommand',
        ['handler', 'command', 'shortcut', 'description', 'arg_type', 'hidden',
            'case_sensitive'])

COMMANDS = {}

@export
def parse_special_command(sql):
    command, _, arg = sql.partition(' ')
    return (command, arg.strip())

@export
def special_command(command, shortcut, description, arg_type=PARSED_QUERY,
        hidden=False, case_sensitive=False, aliases=()):
    def wrapper(wrapped):
        register_special_command(wrapped, command, shortcut, description,
                arg_type, hidden, case_sensitive, aliases)
        return wrapped
    return wrapper

@export
def register_special_command(handler, command, shortcut, description,
        arg_type=PARSED_QUERY, hidden=False, case_sensitive=False, aliases=()):
    cmd = command.lower() if not case_sensitive else command
    COMMANDS[cmd] = SpecialCommand(handler, command, shortcut, description,
                                   arg_type, hidden, case_sensitive)
    for alias in aliases:
        cmd = alias.lower() if not case_sensitive else alias
        COMMANDS[cmd] = SpecialCommand(handler, command, shortcut, description,
                                       arg_type, case_sensitive=case_sensitive,
                                       hidden=True)

@export
def execute(cur, sql):
    """Execute a special command and return the results. If the special command
    is not supported a KeyError will be raised.
    """
    command, arg = parse_special_command(sql)

    try:
        special_cmd = COMMANDS[command]
    except KeyError:
        special_cmd = COMMANDS[command.lower()]
        if special_cmd.case_sensitive:
            raise KeyError('Command not found: %s' % command)

    if special_cmd.arg_type == NO_QUERY:
        return special_cmd.handler()
    elif special_cmd.arg_type == PARSED_QUERY:
        return special_cmd.handler(cur=cur, arg=arg)
    elif special_cmd.arg_type == RAW_QUERY:
        return special_cmd.handler(cur=cur, query=sql)

@special_command('help', '\\?', 'Show this help.', arg_type=NO_QUERY, aliases=('\\?', '?'))
def show_help():  # All the parameters are ignored.
    headers = ['Command', 'Shortcut', 'Description']
    result = []

    for _, value in sorted(COMMANDS.items()):
        if not value.hidden:
            result.append((value.command, value.shortcut, value.description))
    return [(None, result, headers, None)]

@special_command('exit', '\\q', 'Exit.', arg_type=NO_QUERY, aliases=('\\q', ))
@special_command('quit', '\\q', 'Quit.', arg_type=NO_QUERY)
@special_command('\\e', '\\e', 'Edit command with editor. (uses $EDITOR)', arg_type=NO_QUERY, case_sensitive=True)
@special_command('\\G', '\\G', 'Display results vertically.', arg_type=NO_QUERY, case_sensitive=True)
def stub():
    raise NotImplementedError
