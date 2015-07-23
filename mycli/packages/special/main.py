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
class CommandNotFound(Exception):
    pass

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

    if (command not in COMMANDS) and (command.lower() not in COMMANDS):
        raise CommandNotFound

    try:
        special_cmd = COMMANDS[command]
    except KeyError:
        special_cmd = COMMANDS[command.lower()]
        if special_cmd.case_sensitive:
            raise CommandNotFound('Command not found: %s' % command)

    # "help <SQL KEYWORD> is a special case. We want built-in help, not
    # mycli help here.
    if command == 'help' and arg:
        return show_keyword_help(cur=cur, arg=arg)

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

def show_keyword_help(cur, arg):
    """
    Call the built-in "show <command>", to display help for an SQL keyword.
    :param cur: cursor
    :param arg: string
    :return: list
    """
    keyword = arg.strip('"').strip("'")
    query = "help '{0}'".format(keyword)
    log.debug(query)
    cur.execute(query)
    if cur.description and cur.rowcount > 0:
        headers = [x[0] for x in cur.description]
        return [(None, cur, headers, '')]
    else:
        return [(None, None, None, 'No help found for {0}.'.format(keyword))]

@special_command('exit', '\\q', 'Exit.', arg_type=NO_QUERY, aliases=('\\q', ))
@special_command('quit', '\\q', 'Quit.', arg_type=NO_QUERY)
@special_command('\\e', '\\e', 'Edit command with editor. (uses $EDITOR)', arg_type=NO_QUERY, case_sensitive=True)
@special_command('\\G', '\\G', 'Display results vertically.', arg_type=NO_QUERY, case_sensitive=True)
def stub():
    raise NotImplementedError
