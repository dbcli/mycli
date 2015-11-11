#!/usr/bin/env python
from __future__ import unicode_literals
from __future__ import print_function

import os
import sys
import traceback
import logging
import threading
from time import time
from datetime import datetime
from random import choice
from io import open

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

from .packages.tabulate import tabulate, table_formats
from .packages.expanded import expanded_table
from .packages.special.main import (COMMANDS, NO_QUERY)
import mycli.packages.special as special
from .sqlcompleter import SQLCompleter
from .clitoolbar import create_toolbar_tokens_func
from .clistyle import style_factory
from .sqlexecute import SQLExecute
from .clibuffer import CLIBuffer
from .completion_refresher import CompletionRefresher
from .config import (write_default_config, load_config, get_mylogin_cnf_path,
                     open_mylogin_cnf, CryptoError)
from .key_bindings import mycli_bindings
from .encodingutils import utf8tounicode
from .lexer import MyCliLexer
from .__init__ import __version__

click.disable_unicode_literals_warning = True

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
    defaults_suffix = None

    # In order of being loaded. Files lower in list override earlier ones.
    cnf_files = [
        '/etc/my.cnf',
        '/etc/mysql/my.cnf',
        '/usr/local/etc/my.cnf',
        os.path.expanduser('~/.my.cnf')
    ]

    def __init__(self, sqlexecute=None, prompt=None,
            logfile=None, defaults_suffix=None, defaults_file=None,
            login_path=None):
        self.sqlexecute = sqlexecute
        self.logfile = logfile
        self.defaults_suffix = defaults_suffix
        self.login_path = login_path

        # self.cnf_files is a class variable that stores the list of mysql
        # config files to read in at launch.
        # If defaults_file is specified then override the class variable with
        # defaults_file.
        if defaults_file:
            self.cnf_files = [defaults_file]

        default_config = os.path.join(PACKAGE_ROOT, 'myclirc')
        write_default_config(default_config, '~/.myclirc')


        # Load config.
        c = self.config = load_config('~/.myclirc', default_config)
        self.multi_line = c['main'].as_bool('multi_line')
        self.destructive_warning = c['main'].as_bool('destructive_warning')
        self.key_bindings = c['main']['key_bindings']
        special.set_timing_enabled(c['main'].as_bool('timing'))
        self.table_format = c['main']['table_format']
        self.syntax_style = c['main']['syntax_style']
        self.cli_style = c['colors']
        self.wider_completion_menu = c['main'].as_bool('wider_completion_menu')

        # audit log
        if self.logfile is None and 'audit_log' in c['main']:
            try:
                self.logfile = open(os.path.expanduser(c['main']['audit_log']), 'a')
            except (IOError, OSError) as e:
                self.output('Error: Unable to open the audit log file. Your queries will not be logged.', err=True, fg='red')
                self.logfile = False

        self.completion_refresher = CompletionRefresher()

        self.logger = logging.getLogger(__name__)
        self.initialize_logging()

        prompt_cnf = self.read_my_cnf_files(self.cnf_files, ['prompt'])['prompt']
        self.prompt_format = prompt or prompt_cnf or c['main']['prompt'] or \
                             self.default_prompt

        self.query_history = []

        # Initialize completer.
        smart_completion = c['main'].as_bool('smart_completion')
        self.completer = SQLCompleter(smart_completion)
        self._completer_lock = threading.Lock()

        # Register custom special commands.
        self.register_special_commands()

        # Load .mylogin.cnf if it exists.
        mylogin_cnf_path = get_mylogin_cnf_path()
        if mylogin_cnf_path:
            try:
                mylogin_cnf = open_mylogin_cnf(mylogin_cnf_path)
                if mylogin_cnf_path and mylogin_cnf:
                    # .mylogin.cnf gets read last, even if defaults_file is specified.
                    self.cnf_files.append(mylogin_cnf)
                elif mylogin_cnf_path and not mylogin_cnf:
                    # There was an error reading the login path file.
                    print('Error: Unable to read login path file.')
            except CryptoError:
                click.secho('Warning: .mylogin.cnf was not read: pycrypto '
                            'module is not available.')

        self.cli = None

    def register_special_commands(self):
        special.register_special_command(self.change_db, 'use',
                '\\u', 'Change to a new database.', aliases=('\\u',))
        special.register_special_command(self.change_db, 'connect',
                '\\r', 'Reconnect to the database. Optional database argument.',
                aliases=('\\r', ), case_sensitive=True)
        special.register_special_command(self.refresh_completions, 'rehash',
                '\\#', 'Refresh auto-completions.', arg_type=NO_QUERY, aliases=('\\#',))
        special.register_special_command(self.change_table_format, 'tableformat',
                '\\T', 'Change Table Type.', aliases=('\\T',), case_sensitive=True)
        special.register_special_command(self.execute_from_file, 'source', '\\. filename',
                              'Execute commands from file.', aliases=('\\.',))
        special.register_special_command(self.change_prompt_format, 'prompt',
                '\\R', 'Change prompt format.', aliases=('\\R',), case_sensitive=True)

    def change_table_format(self, arg, **_):
        if not arg in table_formats():
            msg = "Table type %s not yet implemented.  Allowed types:" % arg
            for table_type in table_formats():
                msg += "\n\t%s" % table_type
            yield (None, None, None, msg)
        else:
            self.table_format = arg
            yield (None, None, None, "Changed table Type to %s" % self.table_format)

    def change_db(self, arg, **_):
        if arg is None:
            self.sqlexecute.connect()
        else:
            self.sqlexecute.connect(database=arg)

        yield (None, None, None, 'You are now connected to database "%s" as '
                'user "%s"' % (self.sqlexecute.dbname, self.sqlexecute.user))

    def execute_from_file(self, arg, **_):
        if not arg:
            message = 'Missing required argument, filename.'
            return [(None, None, None, message)]
        try:
            with open(os.path.expanduser(arg), encoding='utf-8') as f:
                query = f.read()
        except IOError as e:
            return [(None, None, None, str(e))]

        return self.sqlexecute.run(query)

    def change_prompt_format(self, arg, **_):
        """
        Change the prompt format.
        """
        if not arg:
            message = 'Missing required argument, format.'
            return [(None, None, None, message)]

        self.prompt_format = self.get_prompt(arg)
        return [(None, None, None, "Changed prompt format to %s" % arg)]

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

    def read_my_cnf_files(self, files, keys):
        """
        Reads a list of config files and merges them. The last one will win.
        :param files: list of files to read
        :param keys: list of keys to retrieve
        :returns: tuple, with None for missing keys.
        """
        cnf = ConfigObj()
        for _file in files:
            try:
                cnf.merge(ConfigObj(_file, interpolation=False))
            except ConfigObjError as e:
                self.logger.error('Error parsing %r.', _file)
                self.logger.error('Recovering partially parsed config values.')
                cnf.merge(e.config)
                pass

        sections = ['client']
        if self.login_path and self.login_path != 'client':
            sections.append(self.login_path)

        if self.defaults_suffix:
            sections.extend([sect + self.defaults_suffix for sect in sections])

        def get(key):
            result = None
            for sect in cnf:
                if sect in sections and key in cnf[sect]:
                    result = cnf[sect][key]
            return result

        return dict([(x, get(x)) for x in keys])

    def connect(self, database='', user='', passwd='', host='', port='',
            socket='', charset=''):

        cnf = {'database': None,
               'user': None,
               'password': None,
               'host': None,
               'port': None,
               'socket': None,
               'default-character-set': None}

        cnf = self.read_my_cnf_files(self.cnf_files, cnf.keys())

        # Fall back to config values only if user did not specify a value.

        database = database or cnf['database']
        if port or host:
            socket = ''
        else:
            socket = socket or cnf['socket']
        user = user or cnf['user'] or os.getenv('USER')
        host = host or cnf['host'] or 'localhost'
        port = int(port or cnf['port']) or 3306
        passwd = passwd or cnf['password']
        charset = charset or cnf['default-character-set'] or 'utf8'

        # Connect to the database.

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
        self.set_pager_from_config()

        self.refresh_completions()

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

        get_toolbar_tokens = create_toolbar_tokens_func(lambda: self.key_bindings,
                                                        self.completion_refresher.is_refreshing)

        layout = create_default_layout(lexer=MyCliLexer,
                                       reserve_space_for_menu=True,
                                       multiline=True,
                                       get_prompt_tokens=prompt_tokens,
                                       get_bottom_toolbar_tokens=get_toolbar_tokens,
                                       display_completions_in_columns=self.wider_completion_menu,
                                       extra_input_processors=[
                                           ConditionalProcessor(
                                               processor=HighlightMatchingBracketProcessor(chars='[](){}'),
                                               filter=HasFocus(DEFAULT_BUFFER) & ~IsDone()),
                                       ])
        with self._completer_lock:
            buf = CLIBuffer(always_multiline=self.multi_line, completer=self.completer,
                    history=FileHistory(os.path.expanduser('~/.mycli-history')),
                    complete_while_typing=Always())

            application = Application(style=style_factory(self.syntax_style, self.cli_style),
                                      layout=layout, buffer=buf,
                                      key_bindings_registry=key_binding_manager.registry,
                                      on_exit=AbortAction.RAISE_EXCEPTION,
                                      ignore_case=True)
            self.cli = CommandLineInterface(application=application,
                                       eventloop=create_eventloop())

        try:
            while True:
                document = self.cli.run()

                special.set_expanded_output(False)

                # The reason we check here instead of inside the sqlexecute is
                # because we want to raise the Exit exception which will be
                # caught by the try/except block that wraps the
                # sqlexecute.run() statement.
                if quit_command(document.text):
                    raise EOFError

                try:
                    document = self.handle_editor_command(self.cli, document)
                except RuntimeError as e:
                    logger.error("sql: %r, error: %r", document.text, e)
                    logger.error("traceback: %r", traceback.format_exc())
                    self.output(str(e), err=True, fg='red')
                    continue
                if self.destructive_warning:
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
                    successful = True
                    output = []
                    total = 0
                    for title, cur, headers, status in res:
                        logger.debug("headers: %r", headers)
                        logger.debug("rows: %r", cur)
                        logger.debug("status: %r", status)
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
                except UnicodeDecodeError as e:
                    import pymysql
                    if pymysql.VERSION < ('0', '6', '7'):
                        message = ('You are running an older version of pymysql.\n'
                                'Please upgrade to 0.6.7 or above to view binary data.\n'
                                'Try \'pip install -U pymysql\'.')
                        self.output(message)
                    else:
                        raise e
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
                    try:
                        self.output_via_pager('\n'.join(output))
                    except KeyboardInterrupt:
                        pass
                    if special.is_timing_enabled():
                        self.output('Time: %0.03fs' % total)

                    # Refresh the table names and column names if necessary.
                    if need_completion_refresh(document.text):
                        self.refresh_completions(
                                reset=need_completion_reset(document.text))
                finally:
                    if self.logfile is False:
                        self.output("Warning: This query was not logged.", err=True, fg='red')
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

    def set_pager_from_config(self):
        cnf = self.read_my_cnf_files(self.cnf_files, ['pager'])
        if cnf['pager']:
            special.set_pager(cnf['pager'])

    def refresh_completions(self, reset=False):
        if reset:
            with self._completer_lock:
                self.completer.reset_completions()
        self.completion_refresher.refresh(self.sqlexecute,
                                          self._on_completions_refreshed)

        return [(None, None, None,
                'Auto-completion refresh started in the background.')]

    def _on_completions_refreshed(self, new_completer):
        self._swap_completer_objects(new_completer)

        if self.cli:
            # After refreshing, redraw the CLI to clear the statusbar
            # "Refreshing completions..." indicator
            self.cli.request_redraw()

    def _swap_completer_objects(self, new_completer):
        """Swap the completer object in cli with the newly created completer.
        """
        with self._completer_lock:
            self.completer = new_completer
            # When mycli is first launched we call refresh_completions before
            # instantiating the cli object. So it is necessary to check if cli
            # exists before trying the replace the completer object in cli.
            if self.cli:
                self.cli.current_buffer.completer = new_completer

    def get_completions(self, text, cursor_positition):
        with self._completer_lock:
            return self.completer.get_completions(
                Document(text=text, cursor_position=cursor_positition), None)

    def get_prompt(self, string):
        sqlexecute = self.sqlexecute
        string = string.replace('\\u', sqlexecute.user or '(none)')
        string = string.replace('\\h', sqlexecute.host or '(none)')
        string = string.replace('\\d', sqlexecute.dbname or '(none)')
        string = string.replace('\\t', sqlexecute.server_type()[0] or 'mycli')
        string = string.replace('\\n', "\n")
        return string

@click.command()
@click.option('-h', '--host', envvar='MYSQL_HOST', help='Host address of the database.')
@click.option('-P', '--port', envvar='MYSQL_TCP_PORT', type=int, help='Port number to use for connection. Honors '
              '$MYSQL_TCP_PORT')
@click.option('-u', '--user', help='User name to connect to the database.')
@click.option('-S', '--socket', envvar='MYSQL_UNIX_PORT', help='The socket file to use for connection.')
@click.option('-p', '--password', 'password', envvar='MYSQL_PWD', type=str,
              help='Password to connect to the database')
@click.option('--pass', 'password', envvar='MYSQL_PWD', type=str,
              help='Password to connect to the database')
@click.option('-v', '--version', is_flag=True, help='Version of mycli.')
@click.option('-D', '--database', 'dbname', help='Database to use.')
@click.option('-R', '--prompt', 'prompt',
              help='Prompt format (Default: "{0}")'.format(
                  MyCli.default_prompt))
@click.option('-l', '--logfile', type=click.File(mode='a', encoding='utf-8'),
              help='Log every query and its results to a file.')
@click.option('--defaults-group-suffix', type=str,
              help='Read config group with the specified suffix.')
@click.option('--defaults-file', type=click.Path(),
              help='Only read default options from the given file')
@click.option('--login-path', type=str,
              help='Read this path from the login file.')
@click.argument('database', default='', nargs=1)
def cli(database, user, host, port, socket, password, dbname,
        version, prompt, logfile, defaults_group_suffix, defaults_file,
        login_path):
    if version:
        print('Version:', __version__)
        sys.exit(0)

    mycli = MyCli(prompt=prompt, logfile=logfile,
                  defaults_suffix=defaults_group_suffix,
                  defaults_file=defaults_file, login_path=login_path)

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
            if first_token.lower() in ('alter', 'create', 'use', '\\r',
                    '\\u', 'connect', 'drop'):
                return True
        except Exception:
            return False

def need_completion_reset(queries):
    """Determines if the statement is a database switch such as 'use' or '\\u'.
    When a database is changed the existing completions must be reset before we
    start the completion refresh for the new database.
    """
    for query in sqlparse.split(queries):
        try:
            first_token = query.split()[0]
            if first_token.lower() in ('use', '\\u'):
                return True
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
    destructive = set(['drop', 'shutdown', 'delete', 'truncate'])
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
