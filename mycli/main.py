#!/usr/bin/env python
from __future__ import unicode_literals
from __future__ import print_function

import os
import os.path
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
from prompt_toolkit.interface import AcceptAction
from prompt_toolkit.enums import DEFAULT_BUFFER, EditingMode
from prompt_toolkit.shortcuts import create_prompt_layout, create_eventloop
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
from .config import (write_default_config, get_mylogin_cnf_path,
                     open_mylogin_cnf, CryptoError, read_config_file,
                     read_config_files, str_to_bool)
from .key_bindings import mycli_bindings
from .encodingutils import utf8tounicode
from .lexer import MyCliLexer
from .__init__ import __version__

click.disable_unicode_literals_warning = True

try:
    from urlparse import urlparse
    FileNotFoundError = OSError
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
        '~/.my.cnf'
    ]

    system_config_files = [
		'/etc/myclirc',
    ]

    default_config_file = os.path.join(PACKAGE_ROOT, 'myclirc')
    user_config_file = '~/.myclirc'


    def __init__(self, sqlexecute=None, prompt=None,
            logfile=None, defaults_suffix=None, defaults_file=None,
            login_path=None, auto_vertical_output=False, warn=None):
        self.sqlexecute = sqlexecute
        self.logfile = logfile
        self.defaults_suffix = defaults_suffix
        self.login_path = login_path
        self.auto_vertical_output = auto_vertical_output

        # self.cnf_files is a class variable that stores the list of mysql
        # config files to read in at launch.
        # If defaults_file is specified then override the class variable with
        # defaults_file.
        if defaults_file:
            self.cnf_files = [defaults_file]

        # Load config.
        config_files = ([self.default_config_file] + self.system_config_files +
                        [self.user_config_file])
        c = self.config = read_config_files(config_files)
        self.multi_line = c['main'].as_bool('multi_line')
        self.key_bindings = c['main']['key_bindings']
        special.set_timing_enabled(c['main'].as_bool('timing'))
        self.table_format = c['main']['table_format']
        self.syntax_style = c['main']['syntax_style']
        self.cli_style = c['colors']
        self.wider_completion_menu = c['main'].as_bool('wider_completion_menu')
        c_dest_warning = c['main'].as_bool('destructive_warning')
        self.destructive_warning = c_dest_warning if warn is None else warn

        # Write user config if system config wasn't the last config loaded.
        if c.filename not in self.system_config_files:
            write_default_config(self.default_config_file, self.user_config_file)

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

        if (self.destructive_warning and
                confirm_destructive_query(query) is False):
            message = 'Wise choice. Command execution stopped.'
            return [(None, None, None, message)]

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

        # Only capture warnings on Python 2.7 and later.
        try:
            logging.captureWarnings(True)
        except AttributeError:
            pass

        root_logger.debug('Initializing mycli logging.')
        root_logger.debug('Log file %r.', log_file)

    def connect_uri(self, uri, local_infile=None, ssl=None):
        uri = urlparse(uri)
        database = uri.path[1:]  # ignore the leading fwd slash
        self.connect(database, uri.username, uri.password, uri.hostname,
                uri.port, local_infile=local_infile, ssl=ssl)

    def read_my_cnf_files(self, files, keys):
        """
        Reads a list of config files and merges them. The last one will win.
        :param files: list of files to read
        :param keys: list of keys to retrieve
        :returns: tuple, with None for missing keys.
        """
        cnf = read_config_files(files)

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

    def merge_ssl_with_cnf(self, ssl, cnf):
        """Merge SSL configuration dict with cnf dict"""

        merged = {}
        merged.update(ssl)
        prefix = 'ssl-'
        for k, v in cnf.items():
            # skip unrelated options
            if not k.startswith(prefix):
                continue
            if v is None:
                continue
            # special case because PyMySQL argument is significantly different
            # from commandline
            if k == 'ssl-verify-server-cert':
                merged['check_hostname'] = v
            else:
                # use argument name just strip "ssl-" prefix
                arg = k[len(prefix):]
                merged[arg] = v

        return merged

    def connect(self, database='', user='', passwd='', host='', port='',
            socket='', charset='', local_infile='', ssl=''):

        cnf = {'database': None,
               'user': None,
               'password': None,
               'host': None,
               'port': None,
               'socket': None,
               'default-character-set': None,
               'local-infile': None,
               'loose-local-infile': None,
               'ssl-ca': None,
               'ssl-cert': None,
               'ssl-key': None,
               'ssl-cipher': None,
               'ssl-verify-serer-cert': None,
        }

        cnf = self.read_my_cnf_files(self.cnf_files, cnf.keys())

        # Fall back to config values only if user did not specify a value.

        database = database or cnf['database']
        if port or host:
            socket = ''
        else:
            socket = socket or cnf['socket']
        user = user or cnf['user'] or os.getenv('USER')
        host = host or cnf['host'] or 'localhost'
        port = port or cnf['port'] or 3306
        ssl = ssl or {}

        try:
            port = int(port)
        except ValueError as e:
            self.output("Error: Invalid port number: '{0}'.".format(port),
                        err=True, fg='red')
            exit(1)

        passwd = passwd or cnf['password']
        charset = charset or cnf['default-character-set'] or 'utf8'

        # Favor whichever local_infile option is set.
        for local_infile_option in (local_infile, cnf['local-infile'],
                                    cnf['loose-local-infile'], False):
            try:
                local_infile = str_to_bool(local_infile_option)
                break
            except (TypeError, ValueError):
                pass

        ssl = self.merge_ssl_with_cnf(ssl, cnf)
        # prune lone check_hostname=False
        if not any(v for v in ssl.values()):
            ssl = None

        # Connect to the database.

        try:
            try:
                sqlexecute = SQLExecute(database, user, passwd, host, port,
                        socket, charset, local_infile, ssl)
            except OperationalError as e:
                if ('Access denied for user' in e.args[1]):
                    passwd = click.prompt('Password', hide_input=True,
                                          show_default=False, type=str)
                    sqlexecute = SQLExecute(database, user, passwd, host, port,
                            socket, charset, local_infile, ssl)
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
        self.configure_pager()

        self.refresh_completions()

        project_root = os.path.dirname(PACKAGE_ROOT)
        author_file = os.path.join(project_root, 'AUTHORS')
        sponsor_file = os.path.join(project_root, 'SPONSORS')

        key_binding_manager = mycli_bindings()

        print('Version:', __version__)
        print('Chat: https://gitter.im/dbcli/mycli')
        print('Mail: https://groups.google.com/forum/#!forum/mycli-users')
        print('Home: http://mycli.net')
        print('Thanks to the contributor -', thanks_picker([author_file, sponsor_file]))

        def prompt_tokens(cli):
            return [(Token.Prompt, self.get_prompt(self.prompt_format))]

        def get_continuation_tokens(cli, width):
            return [(Token.Continuation, ' ' * (width - 3) + '-> ')]

        get_toolbar_tokens = create_toolbar_tokens_func(self.completion_refresher.is_refreshing)

        layout = create_prompt_layout(lexer=MyCliLexer,
                                      multiline=True,
                                      get_prompt_tokens=prompt_tokens,
                                      get_continuation_tokens=get_continuation_tokens,
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
                    complete_while_typing=Always(), accept_action=AcceptAction.RETURN_DOCUMENT)

            if self.key_bindings == 'vi':
                editing_mode = EditingMode.VI
            else:
                editing_mode = EditingMode.EMACS

            application = Application(style=style_factory(self.syntax_style, self.cli_style),
                                      layout=layout, buffer=buf,
                                      key_bindings_registry=key_binding_manager.registry,
                                      on_exit=AbortAction.RAISE_EXCEPTION,
                                      on_abort=AbortAction.RETRY,
                                      editing_mode=editing_mode,
                                      ignore_case=True)
            self.cli = CommandLineInterface(application=application,
                                       eventloop=create_eventloop())

        try:
            while True:
                document = self.cli.run(reset_current_buffer=True)

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

                        if self.auto_vertical_output:
                            max_width = self.cli.output.get_size().columns
                        else:
                            max_width = None

                        formatted = format_output(title, cur, headers,
                            status, self.table_format,
                            special.is_expanded_output(), max_width)

                        output.extend(formatted)
                        end = time()
                        total += end - start
                        mutating = mutating or is_mutating(status)
                except UnicodeDecodeError as e:
                    import pymysql
                    if pymysql.VERSION < (0, 6, 7):
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
                        if special.is_pager_enabled():
                            self.output_via_pager('\n'.join(output))
                        else:
                            self.output('\n'.join(output))
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

    def configure_pager(self):
        # Provide sane defaults for less.
        os.environ['LESS'] = '-RXF'

        cnf = self.read_my_cnf_files(self.cnf_files, ['pager', 'skip-pager'])
        if cnf['pager']:
            special.set_pager(cnf['pager'])
        if cnf['skip-pager']:
            special.disable_pager()

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
@click.option('--ssl-ca', help='CA file in PEM format',
              type=click.Path(exists=True))
@click.option('--ssl-capath', help='CA directory')
@click.option('--ssl-cert', help='X509 cert in PEM format',
              type=click.Path(exists=True))
@click.option('--ssl-key', help='X509 key in PEM format',
              type=click.Path(exists=True))
@click.option('--ssl-cipher', help='SSL cipher to use')
@click.option('--ssl-verify-server-cert', is_flag=True,
              help=('Verify server\'s "Common Name" in its cert against '
                    'hostname used when connecting. This option is disabled '
                    'by default'))
# as of 2016-02-15 revocation list is not supported by underling PyMySQL
# library (--ssl-crl and --ssl-crlpath options in vanilla mysql client)
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
@click.option('--auto-vertical-output', is_flag=True,
              help='Automatically switch to vertical output mode if the result is wider than the terminal width.')
@click.option('-t', '--table', is_flag=True,
              help='Display batch output in table format.')
@click.option('--warn/--no-warn', default=None,
              help='Warn before running a destructive query.')
@click.option('--local-infile', type=bool,
              help='Enable/disable LOAD DATA LOCAL INFILE.')
@click.option('--login-path', type=str,
              help='Read this path from the login file.')
@click.argument('database', default='', nargs=1)
def cli(database, user, host, port, socket, password, dbname,
        version, prompt, logfile, defaults_group_suffix, defaults_file,
        login_path, auto_vertical_output, local_infile, ssl_ca, ssl_capath,
        ssl_cert, ssl_key, ssl_cipher, ssl_verify_server_cert, table, warn):

    if version:
        print('Version:', __version__)
        sys.exit(0)

    mycli = MyCli(prompt=prompt, logfile=logfile,
                  defaults_suffix=defaults_group_suffix,
                  defaults_file=defaults_file, login_path=login_path,
                  auto_vertical_output=auto_vertical_output, warn=warn)

    # Choose which ever one has a valid value.
    database = database or dbname

    ssl = {
            'ca': ssl_ca and os.path.expanduser(ssl_ca),
            'cert': ssl_cert and os.path.expanduser(ssl_cert),
            'key': ssl_key and os.path.expanduser(ssl_key),
            'capath': ssl_capath,
            'cipher': ssl_cipher,
            'check_hostname': ssl_verify_server_cert,
            }

    # remove empty ssl options
    ssl = dict((k, v) for (k, v) in ssl.items() if v is not None)
    if database and '://' in database:
        mycli.connect_uri(database, local_infile, ssl)
    else:
        mycli.connect(database, user, password, host, port, socket,
                      local_infile=local_infile, ssl=ssl)

    mycli.logger.debug('Launch Params: \n'
            '\tdatabase: %r'
            '\tuser: %r'
            '\thost: %r'
            '\tport: %r', database, user, host, port)

    if sys.stdin.isatty():
        mycli.run_cli()
    else:
        stdin = click.get_text_stream('stdin')
        stdin_text = stdin.read()

        try:
            sys.stdin = open('/dev/tty')
        except FileNotFoundError:
            mycli.logger.warning('Unable to open TTY as stdin.')

        if (mycli.destructive_warning and
                confirm_destructive_query(stdin_text) is False):
            exit(0)
        try:
            results = mycli.sqlexecute.run(stdin_text)
            for result in results:
                title, cur, headers, status = result
                table_format = mycli.table_format if table else None
                output = format_output(title, cur, headers, None, table_format)
                for line in output:
                    click.echo(line)
        except Exception as e:
            click.secho(str(e), err=True, fg='red')
            exit(1)

def format_output(title, cur, headers, status, table_format, expanded=False, max_width=None):
    output = []
    if title:  # Only print the title if it's not None.
        output.append(title)
    if cur:
        headers = [utf8tounicode(x) for x in headers]
        if expanded:
            output.append(expanded_table(cur, headers))
        elif table_format is not None:
            rows = list(cur)
            tabulated, frows = tabulate(rows, headers, tablefmt=table_format,
                missingval='<null>')
            if (max_width and rows and
                    content_exceeds_width(frows[0], max_width) and
                    headers):
                output.append(expanded_table(rows, headers))
            else:
                output.append(tabulated)
        else:
            output.append('\t'.join(headers))
            for row in cur:
                output.append('\t'.join([str(r) for r in row]))
    if status:  # Only print the status if it's not None.
        output.append(status)
    return output

def content_exceeds_width(row, width):
    # Account for 3 characters between each column
    separator_space = (len(row)*3)
    # Add 2 columns for a bit of buffer
    line_len = sum([len(str(x)) for x in row]) + separator_space + 2
    return line_len > width

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

def query_starts_with(query, prefixes):
    """Check if the query starts with any item from *prefixes*."""
    prefixes = [prefix.lower() for prefix in prefixes]
    formatted_sql = sqlparse.format(query.lower(), strip_comments=True)
    return formatted_sql.split()[0] in prefixes

def queries_start_with(queries, prefixes):
    """Check if any queries start with any item from *prefixes*."""
    for query in sqlparse.split(queries):
        if query and query_starts_with(query, prefixes) is True:
            return True
    return False

def is_destructive(queries):
    keywords = ('drop', 'shutdown', 'delete', 'truncate')
    return queries_start_with(queries, keywords)

def confirm_destructive_query(queries):
    """Check if the query is destructive and prompts the user to confirm.
    Returns:
    None if the query is non-destructive or we can't prompt the user.
    True if the query is destructive and the user wants to proceed.
    False if the query is destructive and the user doesn't want to proceed.
    """
    prompt_text = ("You're about to run a destructive command.\n"
                   "Do you want to proceed? (y/n)")
    if is_destructive(queries) and sys.stdin.isatty():
        return click.prompt(prompt_text, type=bool)

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
