#!/usr/bin/env python
from __future__ import unicode_literals
from __future__ import print_function

import os
import sys
import traceback
import logging
from time import time
from datetime import datetime
from random import choice

import click
import sqlparse
from prompt_toolkit import CommandLineInterface, Application, AbortAction
from prompt_toolkit.enums import DEFAULT_BUFFER
from prompt_toolkit.shortcuts import create_default_layout, create_eventloop
from prompt_toolkit.document import Document
from prompt_toolkit.filters import Always, HasFocus, IsDone
from prompt_toolkit.layout.processors import (HighlightMatchingBracketProcessor,
                                              ConditionalProcessor)
from prompt_toolkit.history import FileHistory
from pygments.token import Token
from configobj import ConfigObj, ConfigObjError

from .packages.tabulate import tabulate
from .packages.expanded import expanded_table
from .packages.special.main import (COMMANDS, NO_QUERY)
import mycli.packages.special as special
from .sqlcompleter import SQLCompleter
from .clitoolbar import create_toolbar_tokens_func
from .clistyle import style_factory
from .sqlexecute import SQLExecute
from .clibuffer import CLIBuffer
from .config import write_default_config, load_config
from .key_bindings import mycli_bindings
from .encodingutils import utf8tounicode
from .lexer import MyCliLexer
from .__init__ import __version__


try:
    from urlparse import urlparse
except ImportError:
    from urllib.parse import urlparse
from pymysql import OperationalError

from collections import namedtuple

# Query tuples are used for maintaining history
Query = namedtuple('Query', ['query', 'successful', 'mutating'])

PACKAGE_ROOT = os.path.dirname(__file__)

class MyCli(object):

    default_prompt = '\\t \\u@\\h:\\d> '

    def __init__(self, force_passwd_prompt=False, sqlexecute=None, prompt=None, logfile=None):

        self.force_passwd_prompt = force_passwd_prompt
        self.sqlexecute = sqlexecute
        self.logfile = logfile

        default_config = os.path.join(PACKAGE_ROOT, 'myclirc')
        write_default_config(default_config, '~/.myclirc')

        # Load config.
        c = self.config = load_config('~/.myclirc', default_config)
        self.multi_line = c['main'].as_bool('multi_line')
        self.key_bindings = c['main']['key_bindings']
        special.set_timing_enabled(c['main'].as_bool('timing'))
        self.table_format = c['main']['table_format']
        self.syntax_style = c['main']['syntax_style']
        self.prompt_format = prompt or c['main']['prompt'] or \
                             self.default_prompt

        self.logger = logging.getLogger(__name__)
        self.initialize_logging()

        self.query_history = []

        # Initialize completer.
        smart_completion = c['main'].as_bool('smart_completion')
        completer = SQLCompleter(smart_completion)
        self.completer = completer

        # Register custom special commands.
        self.register_special_commands()

    def register_special_commands(self):
        special.register_special_command(self.change_db, 'use',
                '\\u', 'Change to a new database.', aliases=('\\u',))
        special.register_special_command(self.change_db, 'connect',
                '\\r', 'Reconnect to the database. Optional database argument.',
                aliases=('\\r', ))
        special.register_special_command(self.refresh_dynamic_completions, 'rehash',
                '\\#', 'Refresh auto-completions.', arg_type=NO_QUERY, aliases=('\\#',))

    def change_db(self, arg, **_):
        if arg is None:
            self.sqlexecute.connect()
        else:
            self.sqlexecute.connect(database=arg)

        yield (None, None, None, 'You are now connected to database "%s" as '
                'user "%s"' % (self.sqlexecute.dbname, self.sqlexecute.user))

    def initialize_logging(self):

        log_file = self.config['main']['log_file']
        log_level = self.config['main']['log_level']

        level_map = {'CRITICAL': logging.CRITICAL,
                     'ERROR': logging.ERROR,
                     'WARNING': logging.WARNING,
                     'INFO': logging.INFO,
                     'DEBUG': logging.DEBUG
                     }

        handler = logging.FileHandler(os.path.expanduser(log_file))

        formatter = logging.Formatter(
            '%(asctime)s (%(process)d/%(threadName)s) '
            '%(name)s %(levelname)s - %(message)s')

        handler.setFormatter(formatter)

        root_logger = logging.getLogger('mycli')
        root_logger.addHandler(handler)
        root_logger.setLevel(level_map[log_level.upper()])

        root_logger.debug('Initializing mycli logging.')
        root_logger.debug('Log file %r.', log_file)

    def connect_uri(self, uri):
        uri = urlparse(uri)
        database = uri.path[1:]  # ignore the leading fwd slash
        self.connect(database, uri.username, uri.password, uri.hostname,
                uri.port)

    def read_my_cnf_files(self, files):
        """Reads a list of config files and merges them. The last one will win.
        Returns: user, host, port, socket, password, charset. None for missing
        values.
        """
        cnf = ConfigObj()
        for _file in files:
            try:
                cnf.merge(ConfigObj(os.path.expanduser(_file),
                    interpolation=False))
            except ConfigObjError as e:
                self.logger.error('Error parsing %r.', _file)
                self.logger.error('Recovering partially parsed config values.')
                cnf.merge(e.config)
                pass

        def get(key):
            try:
                return cnf['client'][key]
            except KeyError:
                return None

        return (get('database'), get('user'), get('password'), get('host'),
                get('port'), get('socket'), get('default-character-set'),)

    def connect(self, database='', user='', passwd='', host='', port='',
            socket='', charset=''):

        cnf_files = ['/etc/my.cnf', '/etc/mysql/my.cnf',
                '/usr/local/etc/my.cnf', '~/.my.cnf']
        c_database, c_user, c_password, c_host, c_port, c_socket, c_charset = \
                                            self.read_my_cnf_files(cnf_files)

        # Fall back to config values only if user did not specify a value.

        database = database or c_database
        if port or host:
            socket = ''
        else:
            socket = socket or c_socket
        user = user or c_user or os.getenv('USER')
        host = host or c_host or 'localhost'
        port = int(port or c_port or os.getenv('MYSQL_TCP_PORT') or 3306)
        passwd = passwd or c_password
        charset = charset or c_charset or 'utf8'

        # Connect to the database.

        # Prompt for a password immediately if requested via the -p flag. This
        # avoids wasting time trying to connect to the database and catching a
        # no-password exception.
        # If we successfully parsed a password from a URI, there's no need to
        # prompt for it, even with the -p flag
        if self.force_passwd_prompt and not passwd:
            passwd = click.prompt('Password', hide_input=True,
                                  show_default=False, type=str)

        try:
            try:
                sqlexecute = SQLExecute(database, user, passwd, host, port,
                        socket, charset)
            except OperationalError as e:
                if ('Access denied for user' in e.args[1]):
                    passwd = click.prompt('Password', hide_input=True,
                                          show_default=False, type=str)
                    sqlexecute = SQLExecute(database, user, passwd, host, port,
                            socket, charset)
                else:
                    raise e
        except Exception as e:  # Connecting to a database could fail.
            self.logger.debug('Database connection failed: %r.', e)
            self.logger.error("traceback: %r", traceback.format_exc())
            self.output(str(e), err=True, fg='red')
            exit(1)

        self.sqlexecute = sqlexecute

    def handle_editor_command(self, cli, document):
        """
        Editor command is any query that is prefixed or suffixed
        by a '\e'. The reason for a while loop is because a user
        might edit a query multiple times.
        For eg:
        "select * from \e"<enter> to edit it in vim, then come
        back to the prompt with the edited query "select * from
        blah where q = 'abc'\e" to edit it again.
        :param cli: CommandLineInterface
        :param document: Document
        :return: Document
        """
        while special.editor_command(document.text):
            filename = special.get_filename(document.text)
            sql, message = special.open_external_editor(filename,
                                                          sql=document.text)
            if message:
                # Something went wrong. Raise an exception and bail.
                raise RuntimeError(message)
            cli.current_buffer.document = Document(sql, cursor_position=len(sql))
            document = cli.run(False)
            continue
        return document

    def run_cli(self):
        sqlexecute = self.sqlexecute
        logger = self.logger
        original_less_opts = self.adjust_less_opts()

        self.initialize_completions()
        completer = self.completer

        def set_key_bindings(value):
            if value not in ('emacs', 'vi'):
                value = 'emacs'
            self.key_bindings = value

        project_root = os.path.dirname(PACKAGE_ROOT)
        author_file = os.path.join(project_root, 'AUTHORS')
        sponsor_file = os.path.join(project_root, 'SPONSORS')

        key_binding_manager = mycli_bindings(get_key_bindings=lambda: self.key_bindings,
                                             set_key_bindings=set_key_bindings)
        print('Version:', __version__)
        print('Chat: https://gitter.im/dbcli/mycli')
        print('Mail: https://groups.google.com/forum/#!forum/mycli-users')
        print('Home: http://mycli.net')
        print('Thanks to the contributor -', thanks_picker([author_file, sponsor_file]))

        def prompt_tokens(cli):
            return [(Token.Prompt, self.get_prompt(self.prompt_format))]

        get_toolbar_tokens = create_toolbar_tokens_func(lambda: self.key_bindings)
        layout = create_default_layout(lexer=MyCliLexer,
                                       reserve_space_for_menu=True,
                                       get_prompt_tokens=prompt_tokens,
                                       get_bottom_toolbar_tokens=get_toolbar_tokens,
                                       extra_input_processors=[
                                           ConditionalProcessor(
                                               processor=HighlightMatchingBracketProcessor(chars='[](){}'),
                                               filter=HasFocus(DEFAULT_BUFFER) & ~IsDone()),
                                       ])
        buf = CLIBuffer(always_multiline=self.multi_line, completer=completer,
                history=FileHistory(os.path.expanduser('~/.mycli-history')),
                complete_while_typing=Always())

        application = Application(style=style_factory(self.syntax_style),
                                  layout=layout, buffer=buf,
                                  key_bindings_registry=key_binding_manager.registry,
                                  on_exit=AbortAction.RAISE_EXCEPTION)
        cli = CommandLineInterface(application=application, eventloop=create_eventloop())

        try:
            while True:
                document = cli.run()

                special.set_expanded_output(False)

                # The reason we check here instead of inside the sqlexecute is
                # because we want to raise the Exit exception which will be
                # caught by the try/except block that wraps the
                # sqlexecute.run() statement.
                if quit_command(document.text):
                    raise EOFError

                try:
                    document = self.handle_editor_command(cli, document)
                except RuntimeError as e:
                    logger.error("sql: %r, error: %r", document.text, e)
                    logger.error("traceback: %r", traceback.format_exc())
                    self.output(str(e), err=True, fg='red')
                    continue

                destroy = confirm_destructive_query(document.text)
                if destroy is None:
                    pass  # Query was not destructive. Nothing to do here.
                elif destroy is True:
                    self.output('Your call!')
                else:
                    self.output('Wise choice!')
                    continue

                # Keep track of whether or not the query is mutating. In case
                # of a multi-statement query, the overall query is considered
                # mutating if any one of the component statements is mutating
                mutating = False

                try:
                    logger.debug('sql: %r', document.text)
                    if self.logfile:
                        self.logfile.write('\n# %s\n' % datetime.now())
                        self.logfile.write(document.text)
                        self.logfile.write('\n')
                    successful = False
                    start = time()
                    res = sqlexecute.run(document.text)
                    duration = time() - start
                    successful = True
                    output = []
                    total = 0
                    for title, cur, headers, status in res:
                        logger.debug("headers: %r", headers)
                        logger.debug("rows: %r", cur)
                        logger.debug("status: %r", status)
                        start = time()
                        threshold = 1000
                        if (is_select(status) and
                                cur and cur.rowcount > threshold):
                            self.output('The result set has more than %s rows.'
                                    % threshold, fg='red')
                            if not click.confirm('Do you want to continue?'):
                                self.output("Aborted!", err=True, fg='red')
                                break
                        output.extend(format_output(title, cur, headers,
                            status, self.table_format))
                        end = time()
                        total += end - start
                        mutating = mutating or is_mutating(status)
                except KeyboardInterrupt:
                    # Restart connection to the database
                    sqlexecute.connect()
                    logger.debug("cancelled query, sql: %r", document.text)
                    self.output("cancelled query", err=True, fg='red')
                except NotImplementedError:
                    self.output('Not Yet Implemented.', fg="yellow")
                except OperationalError as e:
                    logger.debug("Exception: %r", e)
                    reconnect = True
                    if (e.args[0] in (2003, 2006, 2013)):
                        reconnect = click.prompt('Connection reset. Reconnect (Y/n)',
                                show_default=False, type=bool, default=True)
                        if reconnect:
                            logger.debug('Attempting to reconnect.')
                            try:
                                sqlexecute.connect()
                                logger.debug('Reconnected successfully.')
                                self.output('Reconnected!\nTry the command again.', fg='green')
                            except OperationalError as e:
                                logger.debug('Reconnect failed. e: %r', e)
                                self.output(str(e), err=True, fg='red')
                                continue  # If reconnection failed, don't proceed further.
                        else:  # If user chooses not to reconnect, don't proceed further.
                            continue
                    else:
                        logger.error("sql: %r, error: %r", document.text, e)
                        logger.error("traceback: %r", traceback.format_exc())
                        self.output(str(e), err=True, fg='red')
                except Exception as e:
                    logger.error("sql: %r, error: %r", document.text, e)
                    logger.error("traceback: %r", traceback.format_exc())
                    self.output(str(e), err=True, fg='red')
                else:
                    self.output_via_pager('\n'.join(output))
                    if special.is_timing_enabled():
                        self.output('Command Time: %0.03fs' % duration)
                        self.output('Format Time: %0.03fs' % total)

                # Refresh the table names and column names if necessary.
                if need_completion_refresh(document.text):
                    self.refresh_dynamic_completions()

                query = Query(document.text, successful, mutating)
                self.query_history.append(query)

        except EOFError:
            self.output('Goodbye!')
        finally:  # Reset the less opts back to original.
            logger.debug('Restoring env var LESS to %r.', original_less_opts)
            os.environ['LESS'] = original_less_opts
            os.environ['PAGER'] = special.get_original_pager()

    def output(self, text, **kwargs):
        if self.logfile:
            self.logfile.write(utf8tounicode(text))
            self.logfile.write('\n')
        click.secho(text, **kwargs)

    def output_via_pager(self, text):
        if self.logfile:
            self.logfile.write(text)
            self.logfile.write('\n')
        click.echo_via_pager(text)

    def adjust_less_opts(self):
        less_opts = os.environ.get('LESS', '')
        self.logger.debug('Original value for LESS env var: %r', less_opts)
        os.environ['LESS'] = '-SRXF'

        return less_opts

    def initialize_completions(self):
        completer = self.completer

        # special_commands
        completer.extend_special_commands(COMMANDS.keys())

        # Items to complete after the SHOW command.
        completer.extend_show_items(self.sqlexecute.show_candidates())

        return self.refresh_dynamic_completions()

    def refresh_dynamic_completions(self):
        sqlexecute = self.sqlexecute

        completer = self.completer
        completer.reset_completions()

        # databases
        completer.extend_database_names(sqlexecute.databases())

        # schemata - In MySQL Schema is the same as database. But for mycli
        # schemata will be the name of the current database.
        completer.extend_schemata(self.sqlexecute.dbname)
        completer.set_dbname(self.sqlexecute.dbname)

        # tables
        completer.extend_relations(sqlexecute.tables(), kind='tables')
        completer.extend_columns(sqlexecute.table_columns(), kind='tables')

        # users
        completer.extend_users(sqlexecute.users())

        # views
        #completer.extend_relations(sqlexecute.views(), kind='views')
        #completer.extend_columns(sqlexecute.view_columns(), kind='views')

        # functions
        completer.extend_functions(sqlexecute.functions())

        return [(None, None, None, 'Auto-completion refreshed.')]

    def get_completions(self, text, cursor_positition):
        return self.completer.get_completions(
            Document(text=text, cursor_position=cursor_positition), None)

    def get_prompt(self, string):
        sqlexecute = self.sqlexecute
        string = string.replace('\\u', sqlexecute.user or '(none)')
        string = string.replace('\\h', sqlexecute.host or '(none)')
        string = string.replace('\\d', sqlexecute.dbname or '(none)')
        string = string.replace('\\t', sqlexecute.server_type()[0] or 'mycli')
        return string

@click.command()
@click.option('-h', '--host', help='Host address of the database.')
@click.option('-P', '--port', help='Port number to use for connection. Honors '
              '$MYSQL_TCP_PORT')
@click.option('-u', '--user', help='User name to connect to the database.')
@click.option('-S', '--socket', help='The socket file to use for connection.')
@click.option('-p', '--password', 'prompt_passwd', is_flag=True, default=False,
        help='Force password prompt.')
@click.option('--pass', 'password', envvar='MYCLI_PASSWORD', type=str,
              help='Password to connect to the database')
@click.option('-v', '--version', is_flag=True, help='Version of mycli.')
@click.option('-D', '--database', 'dbname', help='Database to use.')
@click.option('-R', '--prompt', 'prompt',
              help='Prompt format (Default: "{0}")'.format(
                  MyCli.default_prompt))
@click.option('-l', '--logfile', type=click.File(mode='a', encoding='utf-8'),
              help='Log every query and its results to a file.')
@click.argument('database', default='', nargs=1)
def cli(database, user, host, port, socket, password, prompt_passwd, dbname,
        version, prompt, logfile):

    if version:
        print('Version:', __version__)
        sys.exit(0)

    mycli = MyCli(prompt_passwd, prompt=prompt, logfile=logfile)

    # Choose which ever one has a valid value.
    database = database or dbname

    if database and '://' in database:
        mycli.connect_uri(database)
    else:
        mycli.connect(database, user, password, host, port, socket)

    mycli.logger.debug('Launch Params: \n'
            '\tdatabase: %r'
            '\tuser: %r'
            '\thost: %r'
            '\tport: %r', database, user, host, port)

    mycli.run_cli()

def format_output(title, cur, headers, status, table_format):
    output = []
    if title:  # Only print the title if it's not None.
        output.append(title)
    if cur:
        headers = [utf8tounicode(x) for x in headers]
        if special.is_expanded_output():
            output.append(expanded_table(cur, headers))
        else:
            output.append(tabulate(cur, headers, tablefmt=table_format,
                missingval='<null>'))
    if status:  # Only print the status if it's not None.
        output.append(status)
    return output

def need_completion_refresh(queries):
    """Determines if the completion needs a refresh by checking if the sql
    statement is an alter, create, drop or change db."""
    for query in sqlparse.split(queries):
        try:
            first_token = query.split()[0]
            res = first_token.lower() in ('alter', 'create', 'use', '\\r',
                    '\\u', '\\connect', 'drop')
            return res
        except Exception:
            return False

def is_mutating(status):
    """Determines if the statement is mutating based on the status."""
    if not status:
        return False

    mutating = set(['insert', 'update', 'delete', 'alter', 'create', 'drop',
                    'replace', 'truncate', 'load'])
    return status.split(None, 1)[0].lower() in mutating

def is_select(status):
    """Returns true if the first word in status is 'select'."""
    if not status:
        return False
    return status.split(None, 1)[0].lower() == 'select'

def confirm_destructive_query(queries):
    """Checks if the query is destructive and prompts the user to confirm.
    Returns:
    None if the query is non-destructive.
    True if the query is destructive and the user wants to proceed.
    False if the query is destructive and the user doesn't want to proceed.
    """
    destructive = set(['drop', 'shutdown'])
    queries = queries.strip()
    for query in sqlparse.split(queries):
        try:
            first_token = query.split()[0]
            if first_token.lower() in destructive:
                destroy = click.prompt("You're about to run a destructive command.\nDo you want to proceed? (y/n)",
                         type=bool)
                return destroy
        except Exception:
            return False

def quit_command(sql):
    return (sql.strip().lower() == 'exit'
            or sql.strip().lower() == 'quit'
            or sql.strip() == '\q'
            or sql.strip() == ':q')

def thanks_picker(files=()):
    for filename in files:
        with open(filename) as f:
            contents = f.readlines()

    return choice([x.split('*')[1].strip() for x in contents if x.startswith('*')])


if __name__ == "__main__":
    cli()
