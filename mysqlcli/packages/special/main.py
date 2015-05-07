from collections import namedtuple
from helpers import (start, end)
import iocommands
import dbcommands

def show_help(*args):
    title = None
    header = ['Command', 'Shortcut', 'Description']
    footer = None
    result = [(x.name, x.shortcut, x.help) for _, x in sorted(SpecialCommands.commands)]
    return [(title, result, header, footer)]

def stub(*args):
    raise NotImplementedError

# Meta data about each special command.
# name - Name of the special command.
# shortcut - Short form that typically starts with a slash,
# help - docstring for the command,
# handler - function or sql to execute to produce results for the special cmd,
# detector - a function  to detect if an sql command matches the command
SpecialCommand = namedtuple('SpecialCommand',
        ['name', 'shortcut', 'help', 'handler', 'detector'])

class SpecialCommands(object):
    commands = [
            SpecialCommand('?', '\\?', 'Display this help.', show_help, start),
            SpecialCommand('help', '\h', 'Display this help.', show_help,
                start),
            SpecialCommand('connect', '\\r', 'Reconnect to the server',
                dbcommands.reconnect, start),
            SpecialCommand('use', '\\u', 'Change database.',
                dbcommands.reconnect, start),
            SpecialCommand('\\G', '\\G', 'Display results vertically.', stub,
                end),
            SpecialCommand('\\l', '\\l', 'List all databases.',
                'SHOW DATABASES', start),
            SpecialCommand('\\dt', '\\dt',
                'List all tables in current database.', 'SHOW TABLES', start),
            SpecialCommand('exit', '\\q', 'Exit mysql.', stub, start),
            SpecialCommand('quit', '\\q', 'Exit mysql.', stub, start),
            SpecialCommand('rehash', '\\#', 'Rebuild completion hash.',
                dbcommands.refresh_completions, start),
            ]

    def detect(self, statement):
        for command in self.commands:
            if (command.detector(command.name, statement) or
                    command.detector(command.shortcut, statement)):
                return command

    def execute(self, cur, sql, executor=None):
        """Execute a special command and return the results. If the special command
        is not supported None will be returned.

        executor - An object that honors a connect() method. This is used by
        \\r in mysql or \c in postgres.
        """

        command = self.detect(sql)
        if command is None:
            return None

        handler = command.handler
        if callable(handler):
            return handler(cur, sql, executor)
        elif isinstance(handler, str):
            cur.execute(handler)
            if cur.description:
                headers = [x[0] for x in cur.description]
                return [(None, cur, headers, None)]
            else:
                return [(None, None, None, None)]

    @classmethod
    def names(self):
        for command in self.commands:
            yield command.name
            yield command.shortcut

if __name__ == '__main__':
    sp = SpecialCommands()
    import pymysql
    c = pymysql.connect(database='dirac', user='root', host='')
    cur = c.cursor()
    print sp.execute(cur, '\l')
