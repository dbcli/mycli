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

from cli_helpers.tabular_output import TabularOutputFormatter
from cli_helpers.tabular_output import preprocessors
import click
import sqlparse
from prompt_toolkit import CommandLineInterface, Application, AbortAction
from prompt_toolkit.interface import AcceptAction
from prompt_toolkit.enums import DEFAULT_BUFFER, EditingMode
from prompt_toolkit.shortcuts import create_prompt_layout, create_eventloop
from prompt_toolkit.styles.from_pygments import style_from_pygments
from prompt_toolkit.document import Document
from prompt_toolkit.filters import Always, HasFocus, IsDone
from prompt_toolkit.layout.processors import (HighlightMatchingBracketProcessor,
                                              ConditionalProcessor)
from prompt_toolkit.history import FileHistory
from prompt_toolkit.auto_suggest import AutoSuggestFromHistory
from pygments.token import Token

from .packages.special.main import NO_QUERY
from .packages.prompt_utils import confirm_destructive_query
from .packages.tabular_output import sql_format
import mycli.packages.special as special
from .sqlcompleter import SQLCompleter
from .clitoolbar import create_toolbar_tokens_func
from .clistyle import style_factory
from .sqlexecute import FIELD_TYPES, SQLExecute
from .clibuffer import CLIBuffer
from .completion_refresher import CompletionRefresher
from .config import (write_default_config, get_mylogin_cnf_path,
                     open_mylogin_cnf, read_config_files, str_to_bool)
from .key_bindings import mycli_bindings
from .encodingutils import utf8tounicode, text_type
from .lexer import MyCliLexer
from .__init__ import __version__
from mycli.compat import WIN

import itertools

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

PACKAGE_ROOT = os.path.abspath(os.path.dirname(__file__))


class MyCli(object):

    default_prompt = '\\t \\u@\\h:\\d> '
    max_len_prompt = 45
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


    def __init__(self, sqlexecute=None, prompt=None,
            logfile=None, defaults_suffix=None, defaults_file=None,
            login_path=None, auto_vertical_output=False, warn=None,
            myclirc="~/.myclirc"):
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

        # Load config.
        config_files = ([self.default_config_file] + self.system_config_files +
                        [myclirc])
        c = self.config = read_config_files(config_files)
        self.multi_line = c['main'].as_bool('multi_line')
        self.key_bindings = c['main']['key_bindings']
        special.set_timing_enabled(c['main'].as_bool('timing'))
        self.formatter = TabularOutputFormatter(
            format_name=c['main']['table_format'])
        sql_format.register_new_formatter(self.formatter)
        self.formatter.mycli = self
        self.syntax_style = c['main']['syntax_style']
        self.less_chatty = c['main'].as_bool('less_chatty')
        self.cli_style = c['colors']
        self.output_style = style_factory(self.syntax_style, self.cli_style)
        self.wider_completion_menu = c['main'].as_bool('wider_completion_menu')
        c_dest_warning = c['main'].as_bool('destructive_warning')
        self.destructive_warning = c_dest_warning if warn is None else warn
        self.login_path_as_host = c['main'].as_bool('login_path_as_host')

        # read from cli argument or user config file
        self.auto_vertical_output = auto_vertical_output or \
                                c['main'].as_bool('auto_vertical_output')

        # Write user config if system config wasn't the last config loaded.
        if c.filename not in self.system_config_files:
            write_default_config(self.default_config_file, myclirc)

        # audit log
        if self.logfile is None and 'audit_log' in c['main']:
            try:
                self.logfile = open(os.path.expanduser(c['main']['audit_log']), 'a')
            except (IOError, OSError) as e:
                self.echo('Error: Unable to open the audit log file. Your queries will not be logged.',
                          err=True, fg='red')
                self.logfile = False

        self.completion_refresher = CompletionRefresher()

        self.logger = logging.getLogger(__name__)
        self.initialize_logging()

        prompt_cnf = self.read_my_cnf_files(self.cnf_files, ['prompt'])['prompt']
        self.prompt_format = prompt or prompt_cnf or c['main']['prompt'] or \
                             self.default_prompt
        self.prompt_continuation_format = c['main']['prompt_continuation']
        keyword_casing = c['main'].get('keyword_casing', 'auto')

        self.query_history = []

        # Initialize completer.
        self.smart_completion = c['main'].as_bool('smart_completion')
        self.completer = SQLCompleter(
            self.smart_completion,
            supported_formats=self.formatter.supported_formats,
            keyword_casing=keyword_casing)
        self._completer_lock = threading.Lock()

        # Register custom special commands.
        self.register_special_commands()

        # Load .mylogin.cnf if it exists.
        mylogin_cnf_path = get_mylogin_cnf_path()
        if mylogin_cnf_path:
            mylogin_cnf = open_mylogin_cnf(mylogin_cnf_path)
            if mylogin_cnf_path and mylogin_cnf:
                # .mylogin.cnf gets read last, even if defaults_file is specified.
                self.cnf_files.append(mylogin_cnf)
            elif mylogin_cnf_path and not mylogin_cnf:
                # There was an error reading the login path file.
                print('Error: Unable to read login path file.')

        self.cli = None

    def register_special_commands(self):
        special.register_special_command(self.change_db, 'use',
                '\\u', 'Change to a new database.', aliases=('\\u',))
        special.register_special_command(self.change_db, 'connect',
                '\\r', 'Reconnect to the database. Optional database argument.',
                aliases=('\\r', ), case_sensitive=True)
        special.register_special_command(self.refresh_completions, 'rehash',
                '\\#', 'Refresh auto-completions.', arg_type=NO_QUERY, aliases=('\\#',))
        special.register_special_command(
            self.change_table_format, 'tableformat', '\\T',
            'Change the table format used to output results.',
            aliases=('\\T',), case_sensitive=True)
        special.register_special_command(self.execute_from_file, 'source', '\\. filename',
                              'Execute commands from file.', aliases=('\\.',))
        special.register_special_command(self.change_prompt_format, 'prompt',
                '\\R', 'Change prompt format.', aliases=('\\R',), case_sensitive=True)

    def change_table_format(self, arg, **_):
        try:
            self.formatter.format_name = arg
            yield (None, None, None,
                   'Changed table format to {}'.format(arg))
        except ValueError:
            msg = 'Table format {} not recognized. Allowed formats:'.format(
                arg)
            for table_type in self.formatter.supported_formats:
                msg += "\n\t{}".format(table_type)
            yield (None, None, None, msg)

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

        # Disable logging if value is NONE by switching to a no-op handler
        # Set log level to a high value so it doesn't even waste cycles getting called.
        if log_level.upper() == "NONE":
            handler = logging.NullHandler()
            log_level = "CRITICAL"
        else:
            handler = logging.FileHandler(os.path.expanduser(log_file))

        formatter = logging.Formatter(
            '%(asctime)s (%(process)d/%(threadName)s) '
            '%(name)s %(levelname)s - %(message)s')

        handler.setFormatter(formatter)

        root_logger = logging.getLogger('mycli')
        root_logger.addHandler(handler)
        root_logger.setLevel(level_map[log_level.upper()])

        logging.captureWarnings(True)

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

        return {x: get(x) for x in keys}

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
        host = host or cnf['host']
        port = port or cnf['port']
        ssl = ssl or {}

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

        def _connect():
            try:
                self.sqlexecute = SQLExecute(database, user, passwd, host, port,
                                             socket, charset, local_infile, ssl)
            except OperationalError as e:
                if ('Access denied for user' in e.args[1]):
                    new_passwd = click.prompt('Password', hide_input=True,
                                              show_default=False, type=str)
                    self.sqlexecute = SQLExecute(database, user, new_passwd, host, port,
                                                 socket, charset, local_infile, ssl)
                else:
                    raise e

        try:
            if (socket is host is port is None) and not WIN:
                # Try a sensible default socket first (simplifies auth)
                # If we get a connection error, try tcp/ip localhost
                try:
                    socket = '/var/run/mysqld/mysqld.sock'
                    _connect()
                except OperationalError as e:
                    # These are "Can't open socket" and 2x "Can't connect"
                    if [code for code in (2001, 2002, 2003) if code == e.args[0]]:
                        self.logger.debug('Database connection failed: %r.', e)
                        self.logger.error(
                            "traceback: %r", traceback.format_exc())
                        self.logger.debug('Retrying over TCP/IP')
                        self.echo(str(e), err=True)
                        self.echo(
                            'Failed to connect by socket, retrying over TCP/IP', err=True)

                        # Else fall back to TCP/IP localhost
                        socket = ""
                        host = 'localhost'
                        port = 3306
                        _connect()
                    else:
                        raise e
            else:
                host = host or 'localhost'
                port = port or 3306

                # Bad ports give particularly daft error messages
                try:
                    port = int(port)
                except ValueError as e:
                    self.echo("Error: Invalid port number: '{0}'.".format(port),
                              err=True, fg='red')
                    exit(1)

                _connect()
        except Exception as e:  # Connecting to a database could fail.
            self.logger.debug('Database connection failed: %r.', e)
            self.logger.error("traceback: %r", traceback.format_exc())
            self.echo(str(e), err=True, fg='red')
            exit(1)

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
        # FIXME: using application.pre_run_callables like this here is not the best solution.
        # It's internal api of prompt_toolkit that may change. This was added to fix
        # https://github.com/dbcli/pgcli/issues/668. We may find a better way to do it in the future.
        saved_callables = cli.application.pre_run_callables
        while special.editor_command(document.text):
            filename = special.get_filename(document.text)
            query = (special.get_editor_query(document.text) or
                     self.get_last_query())
            sql, message = special.open_external_editor(filename, sql=query)
            if message:
                # Something went wrong. Raise an exception and bail.
                raise RuntimeError(message)
            cli.current_buffer.document = Document(sql, cursor_position=len(sql))
            cli.application.pre_run_callables = []
            document = cli.run()
            continue
        cli.application.pre_run_callables = saved_callables
        return document

    def run_cli(self):
        iterations = 0
        sqlexecute = self.sqlexecute
        logger = self.logger
        self.configure_pager()

        if self.smart_completion:
            self.refresh_completions()

        author_file = os.path.join(PACKAGE_ROOT, 'AUTHORS')
        sponsor_file = os.path.join(PACKAGE_ROOT, 'SPONSORS')

        key_binding_manager = mycli_bindings()

        if not self.less_chatty:
            print('Version:', __version__)
            print('Chat: https://gitter.im/dbcli/mycli')
            print('Mail: https://groups.google.com/forum/#!forum/mycli-users')
            print('Home: http://mycli.net')
            print('Thanks to the contributor -', thanks_picker([author_file, sponsor_file]))

        def prompt_tokens(cli):
            prompt = self.get_prompt(self.prompt_format)
            if self.prompt_format == self.default_prompt and len(prompt) > self.max_len_prompt:
                prompt = self.get_prompt('\\d> ')
            return [(Token.Prompt, prompt)]

        def get_continuation_tokens(cli, width):
            continuation_prompt = self.get_prompt(self.prompt_continuation_format)
            return [(Token.Continuation, ' ' * (width - len(continuation_prompt)) + continuation_prompt)]

        def show_suggestion_tip():
            return iterations < 2

        def one_iteration(document=None):
            if document is None:
                document = self.cli.run()

                special.set_expanded_output(False)

                try:
                    document = self.handle_editor_command(self.cli, document)
                except RuntimeError as e:
                    logger.error("sql: %r, error: %r", document.text, e)
                    logger.error("traceback: %r", traceback.format_exc())
                    self.echo(str(e), err=True, fg='red')
                    return

            if not document.text.strip():
                return

            if self.destructive_warning:
                destroy = confirm_destructive_query(document.text)
                if destroy is None:
                    pass  # Query was not destructive. Nothing to do here.
                elif destroy is True:
                    self.echo('Your call!')
                else:
                    self.echo('Wise choice!')
                    return

            # Keep track of whether or not the query is mutating. In case
            # of a multi-statement query, the overall query is considered
            # mutating if any one of the component statements is mutating
            mutating = False

            try:
                logger.debug('sql: %r', document.text)

                special.write_tee(self.get_prompt(self.prompt_format) + document.text)
                if self.logfile:
                    self.logfile.write('\n# %s\n' % datetime.now())
                    self.logfile.write(document.text)
                    self.logfile.write('\n')

                successful = False
                start = time()
                res = sqlexecute.run(document.text)
                self.formatter.query = document.text
                successful = True
                result_count = 0
                for title, cur, headers, status in res:
                    logger.debug("headers: %r", headers)
                    logger.debug("rows: %r", cur)
                    logger.debug("status: %r", status)
                    threshold = 1000
                    if (is_select(status) and
                            cur and cur.rowcount > threshold):
                        self.echo('The result set has more than {} rows.'.format(
                            threshold), fg='red')
                        if not click.confirm('Do you want to continue?'):
                            self.echo("Aborted!", err=True, fg='red')
                            break

                    if self.auto_vertical_output:
                        max_width = self.cli.output.get_size().columns
                    else:
                        max_width = None

                    formatted = self.format_output(
                        title, cur, headers, special.is_expanded_output(),
                        max_width)

                    t = time() - start
                    try:
                        if result_count > 0:
                            self.echo('')
                        try:
                            self.output(formatted, status)
                        except KeyboardInterrupt:
                            pass
                        if special.is_timing_enabled():
                            self.echo('Time: %0.03fs' % t)
                    except KeyboardInterrupt:
                        pass

                    start = time()
                    result_count += 1
                    mutating = mutating or is_mutating(status)
                special.unset_once_if_written()
            except EOFError as e:
                raise e
            except KeyboardInterrupt:
                # get last connection id
                connection_id_to_kill = sqlexecute.connection_id
                logger.debug("connection id to kill: %r", connection_id_to_kill)
                # Restart connection to the database
                sqlexecute.connect()
                try:
                    for title, cur, headers, status in sqlexecute.run('kill %s' % connection_id_to_kill):
                        status_str = str(status).lower()
                        if status_str.find('ok') > -1:
                            logger.debug("cancelled query, connection id: %r, sql: %r",
                                         connection_id_to_kill, document.text)
                            self.echo("cancelled query", err=True, fg='red')
                except Exception as e:
                    self.echo('Encountered error while cancelling query: {}'.format(e),
                              err=True, fg='red')
            except NotImplementedError:
                self.echo('Not Yet Implemented.', fg="yellow")
            except OperationalError as e:
                logger.debug("Exception: %r", e)
                if (e.args[0] in (2003, 2006, 2013)):
                    logger.debug('Attempting to reconnect.')
                    self.echo('Reconnecting...', fg='yellow')
                    try:
                        sqlexecute.connect()
                        logger.debug('Reconnected successfully.')
                        one_iteration(document)
                        return  # OK to just return, cuz the recursion call runs to the end.
                    except OperationalError as e:
                        logger.debug('Reconnect failed. e: %r', e)
                        self.echo(str(e), err=True, fg='red')
                        # If reconnection failed, don't proceed further.
                        return
                else:
                    logger.error("sql: %r, error: %r", document.text, e)
                    logger.error("traceback: %r", traceback.format_exc())
                    self.echo(str(e), err=True, fg='red')
            except Exception as e:
                logger.error("sql: %r, error: %r", document.text, e)
                logger.error("traceback: %r", traceback.format_exc())
                self.echo(str(e), err=True, fg='red')
            else:
                if is_dropping_database(document.text, self.sqlexecute.dbname):
                    self.sqlexecute.dbname = None
                    self.sqlexecute.connect()

                # Refresh the table names and column names if necessary.
                if need_completion_refresh(document.text):
                    self.refresh_completions(
                            reset=need_completion_reset(document.text))
            finally:
                if self.logfile is False:
                    self.echo("Warning: This query was not logged.",
                              err=True, fg='red')
            query = Query(document.text, successful, mutating)
            self.query_history.append(query)

        get_toolbar_tokens = create_toolbar_tokens_func(
            self.completion_refresher.is_refreshing,
            show_suggestion_tip)

        layout = create_prompt_layout(
            lexer=MyCliLexer,
            multiline=True,
            get_prompt_tokens=prompt_tokens,
            get_continuation_tokens=get_continuation_tokens,
            get_bottom_toolbar_tokens=get_toolbar_tokens,
            display_completions_in_columns=self.wider_completion_menu,
            extra_input_processors=[ConditionalProcessor(
                processor=HighlightMatchingBracketProcessor(chars='[](){}'),
                filter=HasFocus(DEFAULT_BUFFER) & ~IsDone()
            )],
            reserve_space_for_menu=self.get_reserved_space()
        )
        with self._completer_lock:
            buf = CLIBuffer(always_multiline=self.multi_line, completer=self.completer,
                            history=FileHistory(os.path.expanduser(
                                os.environ.get('MYCLI_HISTFILE', '~/.mycli-history'))),
                            auto_suggest=AutoSuggestFromHistory(),
                            complete_while_typing=Always(), accept_action=AcceptAction.RETURN_DOCUMENT)

            if self.key_bindings == 'vi':
                editing_mode = EditingMode.VI
            else:
                editing_mode = EditingMode.EMACS

            application = Application(
                style=style_from_pygments(style_cls=self.output_style),
                layout=layout, buffer=buf,
                key_bindings_registry=key_binding_manager.registry,
                on_exit=AbortAction.RAISE_EXCEPTION,
                on_abort=AbortAction.RETRY, editing_mode=editing_mode,
                ignore_case=True)
            self.cli = CommandLineInterface(application=application,
                                       eventloop=create_eventloop())

        try:
            while True:
                one_iteration()
                iterations += 1
        except EOFError:
            special.close_tee()
            if not self.less_chatty:
                self.echo('Goodbye!')

    def log_output(self, output):
        """Log the output in the audit log, if it's enabled."""
        if self.logfile:
            click.echo(utf8tounicode(output), file=self.logfile)

    def echo(self, s, **kwargs):
        """Print a message to stdout.

        The message will be logged in the audit log, if enabled.

        All keyword arguments are passed to click.echo().

        """
        self.log_output(s)
        click.secho(s, **kwargs)

    def get_output_margin(self, status=None):
        """Get the output margin (number of rows for the prompt, footer and
        timing message."""
        margin = self.get_reserved_space() + self.get_prompt(self.prompt_format).count('\n') + 1
        if special.is_timing_enabled():
            margin += 1
        if status:
            margin += 1 + status.count('\n')

        return margin


    def output(self, output, status=None):
        """Output text to stdout or a pager command.

        The status text is not outputted to pager or files.

        The message will be logged in the audit log, if enabled. The
        message will be written to the tee file, if enabled. The
        message will be written to the output file, if enabled.

        """
        if output:
            size = self.cli.output.get_size()

            margin = self.get_output_margin(status)

            fits = True
            buf = []
            output_via_pager = self.explicit_pager and special.is_pager_enabled()
            for i, line in enumerate(output, 1):
                self.log_output(line)
                special.write_tee(line)
                special.write_once(line)

                if fits or output_via_pager:
                    # buffering
                    buf.append(line)
                    if len(line) > size.columns or i > (size.rows - margin):
                        fits = False
                        if not self.explicit_pager and special.is_pager_enabled():
                            # doesn't fit, use pager
                            output_via_pager = True

                        if not output_via_pager:
                            # doesn't fit, flush buffer
                            for line in buf:
                                click.secho(line)
                            buf = []
                else:
                    click.secho(line)

            if buf:
                if output_via_pager:
                    # sadly click.echo_via_pager doesn't accept generators
                    click.echo_via_pager("\n".join(buf))
                else:
                    for line in buf:
                        click.secho(line)

        if status:
            self.log_output(status)
            click.secho(status)

    def configure_pager(self):
        # Provide sane defaults for less if they are empty.
        if not os.environ.get('LESS'):
            os.environ['LESS'] = '-RXF'

        cnf = self.read_my_cnf_files(self.cnf_files, ['pager', 'skip-pager'])
        if cnf['pager']:
            special.set_pager(cnf['pager'])
            self.explicit_pager = True
        else:
            self.explicit_pager = False

        if cnf['skip-pager'] or not self.config['main'].as_bool('enable_pager'):
            special.disable_pager()

    def refresh_completions(self, reset=False):
        if reset:
            with self._completer_lock:
                self.completer.reset_completions()
        self.completion_refresher.refresh(
            self.sqlexecute, self._on_completions_refreshed,
            {'smart_completion': self.smart_completion,
             'supported_formats': self.formatter.supported_formats,
             'keyword_casing': self.completer.keyword_casing})

        return [(None, None, None,
                'Auto-completion refresh started in the background.')]

    def _on_completions_refreshed(self, new_completer):
        """Swap the completer object in cli with the newly created completer.
        """
        with self._completer_lock:
            self.completer = new_completer
            # When mycli is first launched we call refresh_completions before
            # instantiating the cli object. So it is necessary to check if cli
            # exists before trying the replace the completer object in cli.
            if self.cli:
                self.cli.current_buffer.completer = new_completer

        if self.cli:
            # After refreshing, redraw the CLI to clear the statusbar
            # "Refreshing completions..." indicator
            self.cli.request_redraw()

    def get_completions(self, text, cursor_positition):
        with self._completer_lock:
            return self.completer.get_completions(
                Document(text=text, cursor_position=cursor_positition), None)

    def get_prompt(self, string):
        sqlexecute = self.sqlexecute
        host = self.login_path if self.login_path and self.login_path_as_host else sqlexecute.host
        now = datetime.now()
        string = string.replace('\\u', sqlexecute.user or '(none)')
        string = string.replace('\\h', host or '(none)')
        string = string.replace('\\d', sqlexecute.dbname or '(none)')
        string = string.replace('\\t', sqlexecute.server_type()[0] or 'mycli')
        string = string.replace('\\n', "\n")
        string = string.replace('\\D', now.strftime('%a %b %d %H:%M:%S %Y'))
        string = string.replace('\\m', now.strftime('%M'))
        string = string.replace('\\P', now.strftime('%p'))
        string = string.replace('\\R', now.strftime('%H'))
        string = string.replace('\\r', now.strftime('%I'))
        string = string.replace('\\s', now.strftime('%S'))
        string = string.replace('\\p', str(sqlexecute.port))
        string = string.replace('\\_', ' ')
        return string

    def run_query(self, query, new_line=True):
        """Runs *query*."""
        results = self.sqlexecute.run(query)
        for result in results:
            title, cur, headers, status = result
            self.formatter.query = query
            output = self.format_output(title, cur, headers)
            for line in output:
                click.echo(line, nl=new_line)

    def format_output(self, title, cur, headers, expanded=False,
                      max_width=None):
        expanded = expanded or self.formatter.format_name == 'vertical'
        output = []

        output_kwargs = {
            'disable_numparse': True,
            'preserve_whitespace': True,
            'preprocessors': (preprocessors.align_decimals, ),
            'style': self.output_style
        }

        if title:  # Only print the title if it's not None.
            output = itertools.chain(output, [title])

        if cur:
            column_types = None
            if hasattr(cur, 'description'):
                def get_col_type(col):
                    col_type = FIELD_TYPES.get(col[1], text_type)
                    return col_type if type(col_type) is type else text_type
                column_types = [get_col_type(col) for col in cur.description]

            if max_width is not None:
                cur = list(cur)

            formatted = self.formatter.format_output(
                cur, headers, format_name='vertical' if expanded else None,
                column_types=column_types,
                **output_kwargs)

            if isinstance(formatted, (text_type)):
                formatted = formatted.splitlines()
            formatted = iter(formatted)

            first_line = next(formatted)
            formatted = itertools.chain([first_line], formatted)

            if (not expanded and max_width and headers and cur and
                    len(first_line) > max_width):
                formatted = self.formatter.format_output(
                    cur, headers, format_name='vertical', column_types=column_types, **output_kwargs)
                if isinstance(formatted, (text_type)):
                    formatted = iter(formatted.splitlines())

            output = itertools.chain(output, formatted)


        return output

    def get_reserved_space(self):
        """Get the number of lines to reserve for the completion menu."""
        reserved_space_ratio = .45
        max_reserved_space = 8
        _, height = click.get_terminal_size()
        return min(int(round(height * reserved_space_ratio)), max_reserved_space)

    def get_last_query(self):
        """Get the last query executed or None."""
        return self.query_history[-1][0] if self.query_history else None


@click.command()
@click.option('-h', '--host', envvar='MYSQL_HOST', help='Host address of the database.')
@click.option('-P', '--port', envvar='MYSQL_TCP_PORT', type=int, help='Port number to use for connection. Honors '
              '$MYSQL_TCP_PORT.')
@click.option('-u', '--user', help='User name to connect to the database.')
@click.option('-S', '--socket', envvar='MYSQL_UNIX_PORT', help='The socket file to use for connection.')
@click.option('-p', '--password', 'password', envvar='MYSQL_PWD', type=str,
              help='Password to connect to the database.')
@click.option('--pass', 'password', envvar='MYSQL_PWD', type=str,
              help='Password to connect to the database.')
@click.option('--ssl-ca', help='CA file in PEM format.',
              type=click.Path(exists=True))
@click.option('--ssl-capath', help='CA directory.')
@click.option('--ssl-cert', help='X509 cert in PEM format.',
              type=click.Path(exists=True))
@click.option('--ssl-key', help='X509 key in PEM format.',
              type=click.Path(exists=True))
@click.option('--ssl-cipher', help='SSL cipher to use.')
@click.option('--ssl-verify-server-cert', is_flag=True,
              help=('Verify server\'s "Common Name" in its cert against '
                    'hostname used when connecting. This option is disabled '
                    'by default.'))
# as of 2016-02-15 revocation list is not supported by underling PyMySQL
# library (--ssl-crl and --ssl-crlpath options in vanilla mysql client)
@click.option('-v', '--version', is_flag=True, help='Output mycli\'s version.')
@click.option('-D', '--database', 'dbname', help='Database to use.')
@click.option('-d', '--dsn', default='', envvar='DSN',
              help='Use DSN configured into the [alias_dsn] section of myclirc file.')
@click.option('-R', '--prompt', 'prompt',
              help='Prompt format (Default: "{0}").'.format(
                  MyCli.default_prompt))
@click.option('-l', '--logfile', type=click.File(mode='a', encoding='utf-8'),
              help='Log every query and its results to a file.')
@click.option('--defaults-group-suffix', type=str,
              help='Read MySQL config groups with the specified suffix.')
@click.option('--defaults-file', type=click.Path(),
              help='Only read MySQL options from the given file.')
@click.option('--myclirc', type=click.Path(), default="~/.myclirc",
              help='Location of myclirc file.')
@click.option('--auto-vertical-output', is_flag=True,
              help='Automatically switch to vertical output mode if the result is wider than the terminal width.')
@click.option('-t', '--table', is_flag=True,
              help='Display batch output in table format.')
@click.option('--csv', is_flag=True,
              help='Display batch output in CSV format.')
@click.option('--warn/--no-warn', default=None,
              help='Warn before running a destructive query.')
@click.option('--local-infile', type=bool,
              help='Enable/disable LOAD DATA LOCAL INFILE.')
@click.option('--login-path', type=str,
              help='Read this path from the login file.')
@click.option('-e', '--execute',  type=str,
              help='Execute command and quit.')
@click.argument('database', default='', nargs=1)
def cli(database, user, host, port, socket, password, dbname,
        version, prompt, logfile, defaults_group_suffix, defaults_file,
        login_path, auto_vertical_output, local_infile, ssl_ca, ssl_capath,
        ssl_cert, ssl_key, ssl_cipher, ssl_verify_server_cert, table, csv,
        warn, execute, myclirc, dsn):
    """A MySQL terminal client with auto-completion and syntax highlighting.

    \b
    Examples:
      - mycli my_database
      - mycli -u my_user -h my_host.com my_database
      - mycli mysql://my_user@my_host.com:3306/my_database

    """

    if version:
        print('Version:', __version__)
        sys.exit(0)

    mycli = MyCli(prompt=prompt, logfile=logfile,
                  defaults_suffix=defaults_group_suffix,
                  defaults_file=defaults_file, login_path=login_path,
                  auto_vertical_output=auto_vertical_output, warn=warn,
                  myclirc=myclirc)

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
    ssl = {k: v for k, v in ssl.items() if v is not None}
    if dsn is not '':
        try:
            database = mycli.config['alias_dsn'][dsn]
        except:
            click.secho('Invalid DSNs found in the config file. '
                        'Please check the "[alias_dsn]" section in myclirc.',
                        err=True, fg='red')
            exit(1)
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

    #  --execute argument
    if execute:
        try:
            if csv:
                mycli.formatter.format_name = 'csv'
            elif not table:
                mycli.formatter.format_name = 'tsv'

            mycli.run_query(execute)
            exit(0)
        except Exception as e:
            click.secho(str(e), err=True, fg='red')
            exit(1)

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
            new_line = True

            if csv:
                mycli.formatter.format_name = 'csv'
            elif not table:
                mycli.formatter.format_name = 'tsv'

            mycli.run_query(stdin_text, new_line=new_line)
            exit(0)
        except Exception as e:
            click.secho(str(e), err=True, fg='red')
            exit(1)


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


def is_dropping_database(queries, dbname):
    """Determine if the query is dropping a specific database."""
    if dbname is None:
        return False

    def normalize_db_name(db):
        return db.lower().strip('`"')

    dbname = normalize_db_name(dbname)

    for query in sqlparse.parse(queries):
        if query.get_name() is None:
            continue

        first_token = query.token_first(skip_cm=True)
        _, second_token = query.token_next(0, skip_cm=True)
        database_name = normalize_db_name(query.get_name())
        if (first_token.value.lower() == 'drop' and
                second_token.value.lower() in ('database', 'schema') and
                database_name == dbname):
            return True


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


def thanks_picker(files=()):
    for filename in files:
        with open(filename, encoding='utf-8') as f:
            contents = f.readlines()

    return choice([x.split('*')[1].strip() for x in contents if x.startswith('*')])


if __name__ == "__main__":
    cli()
