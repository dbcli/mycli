from __future__ import annotations

from collections import defaultdict, namedtuple
from io import TextIOWrapper
import logging
import os
import re
import shutil
import sys
import threading
import traceback
from typing import Any, Generator, Iterable, Literal

try:
    from pwd import getpwuid
except ImportError:
    pass
from datetime import datetime
from importlib import resources
import itertools
from random import choice
from time import time
from urllib.parse import parse_qs, unquote, urlparse

from cli_helpers.tabular_output import TabularOutputFormatter, preprocessors
from cli_helpers.tabular_output.output_formatter import MISSING_VALUE as DEFAULT_MISSING_VALUE
from cli_helpers.utils import strip_ansi
import click
from configobj import ConfigObj
from prompt_toolkit.auto_suggest import AutoSuggestFromHistory
from prompt_toolkit.completion import Completion, DynamicCompleter
from prompt_toolkit.document import Document
from prompt_toolkit.enums import DEFAULT_BUFFER, EditingMode
from prompt_toolkit.filters import HasFocus, IsDone
from prompt_toolkit.formatted_text import ANSI, AnyFormattedText
from prompt_toolkit.key_binding.bindings.named_commands import register as prompt_register
from prompt_toolkit.key_binding.key_processor import KeyPressEvent
from prompt_toolkit.layout.processors import ConditionalProcessor, HighlightMatchingBracketProcessor
from prompt_toolkit.lexers import PygmentsLexer
from prompt_toolkit.shortcuts import CompleteStyle, PromptSession
import pymysql
from pymysql.constants.ER import HANDSHAKE_ERROR
from pymysql.cursors import Cursor
import sqlglot
import sqlparse

from mycli import __version__
from mycli.clibuffer import cli_is_multiline
from mycli.clistyle import style_factory, style_factory_output
from mycli.clitoolbar import create_toolbar_tokens_func
from mycli.compat import WIN
from mycli.completion_refresher import CompletionRefresher
from mycli.config import get_mylogin_cnf_path, open_mylogin_cnf, read_config_files, str_to_bool, strip_matching_quotes, write_default_config
from mycli.key_bindings import mycli_bindings
from mycli.lexer import MyCliLexer
from mycli.packages import special
from mycli.packages.filepaths import dir_path_exists, guess_socket_location
from mycli.packages.hybrid_redirection import get_redirect_components, is_redirect_command
from mycli.packages.parseutils import is_destructive, is_dropping_database
from mycli.packages.prompt_utils import confirm, confirm_destructive_query
from mycli.packages.special.favoritequeries import FavoriteQueries
from mycli.packages.special.main import ArgType
from mycli.packages.tabular_output import sql_format
from mycli.packages.toolkit.history import FileHistoryWithTimestamp
from mycli.sqlcompleter import SQLCompleter
from mycli.sqlexecute import ERROR_CODE_ACCESS_DENIED, FIELD_TYPES, SQLExecute

try:
    import paramiko
except ImportError:
    from mycli.packages.paramiko_stub import paramiko  # type: ignore[no-redef]


# Query tuples are used for maintaining history
Query = namedtuple("Query", ["query", "successful", "mutating"])

SUPPORT_INFO = "Home: http://mycli.net\nBug tracker: https://github.com/dbcli/mycli/issues"
DEFAULT_WIDTH = 80
DEFAULT_HEIGHT = 25


class MyCli:
    default_prompt = "\\t \\u@\\h:\\d> "
    default_prompt_splitln = "\\u@\\h\\n(\\t):\\d>"
    max_len_prompt = 45
    defaults_suffix = None

    # In order of being loaded. Files lower in list override earlier ones.
    cnf_files: list[str | TextIOWrapper] = [
        "/etc/my.cnf",
        "/etc/mysql/my.cnf",
        "/usr/local/etc/my.cnf",
        os.path.expanduser("~/.my.cnf"),
    ]

    # check XDG_CONFIG_HOME exists and not an empty string
    xdg_config_home = os.environ.get("XDG_CONFIG_HOME", "~/.config")
    system_config_files: list[str | TextIOWrapper] = [
        "/etc/myclirc",
        os.path.join(os.path.expanduser(xdg_config_home), "mycli", "myclirc"),
    ]

    pwd_config_file = os.path.join(os.getcwd(), ".myclirc")

    def __init__(
        self,
        sqlexecute: SQLExecute | None = None,
        prompt: str | None = None,
        logfile: TextIOWrapper | Literal[False] | None = None,
        defaults_suffix: str | None = None,
        defaults_file: str | None = None,
        login_path: str | None = None,
        auto_vertical_output: bool = False,
        show_warnings: bool = False,
        warn: bool | None = None,
        myclirc: str = "~/.myclirc",
    ) -> None:
        self.sqlexecute = sqlexecute
        self.logfile = logfile
        self.defaults_suffix = defaults_suffix
        self.login_path = login_path
        self.toolbar_error_message: str | None = None
        self.prompt_app: PromptSession | None = None

        # self.cnf_files is a class variable that stores the list of mysql
        # config files to read in at launch.
        # If defaults_file is specified then override the class variable with
        # defaults_file.
        if defaults_file:
            self.cnf_files = [defaults_file]

        # Load config.
        config_files: list[str | TextIOWrapper] = self.system_config_files + [myclirc] + [self.pwd_config_file]
        c = self.config = read_config_files(config_files)
        self.multi_line = c["main"].as_bool("multi_line")
        self.key_bindings = c["main"]["key_bindings"]
        special.set_timing_enabled(c["main"].as_bool("timing"))
        special.set_show_favorite_query(c["main"].as_bool("show_favorite_query"))
        self.beep_after_seconds = float(c["main"]["beep_after_seconds"] or 0)

        FavoriteQueries.instance = FavoriteQueries.from_config(self.config)

        self.dsn_alias: str | None = None
        self.main_formatter = TabularOutputFormatter(format_name=c["main"]["table_format"])
        self.redirect_formatter = TabularOutputFormatter(format_name=c["main"].get("redirect_format", "csv"))
        sql_format.register_new_formatter(self.main_formatter)
        sql_format.register_new_formatter(self.redirect_formatter)
        self.main_formatter.mycli = self
        self.redirect_formatter.mycli = self
        self.syntax_style = c["main"]["syntax_style"]
        self.less_chatty = c["main"].as_bool("less_chatty")
        self.cli_style = c["colors"]
        self.output_style = style_factory_output(self.syntax_style, self.cli_style)
        self.wider_completion_menu = c["main"].as_bool("wider_completion_menu")
        c_dest_warning = c["main"].as_bool("destructive_warning")
        self.destructive_warning = c_dest_warning if warn is None else warn
        self.login_path_as_host = c["main"].as_bool("login_path_as_host")
        self.post_redirect_command = c['main'].get('post_redirect_command')
        self.null_string = c['main'].get('null_string')

        # set ssl_mode if a valid option is provided in a config file, otherwise None
        ssl_mode = c["main"].get("ssl_mode", None)
        if ssl_mode not in ("auto", "on", "off", None):
            self.echo(f"Invalid config option provided for ssl_mode ({ssl_mode}); ignoring.", err=True, fg="red")
            self.ssl_mode = None
        else:
            self.ssl_mode = ssl_mode

        # read from cli argument or user config file
        self.auto_vertical_output = auto_vertical_output or c["main"].as_bool("auto_vertical_output")
        self.show_warnings = show_warnings or c["main"].as_bool("show_warnings")

        # Write user config if system config wasn't the last config loaded.
        if c.filename not in self.system_config_files and not os.path.exists(myclirc):
            write_default_config(myclirc)

        # audit log
        if self.logfile is None and "audit_log" in c["main"]:
            try:
                self.logfile = open(os.path.expanduser(c["main"]["audit_log"]), "a")
            except (IOError, OSError):
                self.echo("Error: Unable to open the audit log file. Your queries will not be logged.", err=True, fg="red")
                self.logfile = False

        self.completion_refresher = CompletionRefresher()

        self.logger = logging.getLogger(__name__)
        self.initialize_logging()

        keyword_casing = c["main"].get("keyword_casing", "auto")

        self.query_history: list[Query] = []

        # Initialize completer.
        self.smart_completion = c["main"].as_bool("smart_completion")
        self.completer = SQLCompleter(
            self.smart_completion, supported_formats=self.main_formatter.supported_formats, keyword_casing=keyword_casing
        )
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
                print("Error: Unable to read login path file.")

        self.my_cnf = read_config_files(self.cnf_files, list_values=False)
        prompt_cnf = self.read_my_cnf(self.my_cnf, ["prompt"])["prompt"]
        self.prompt_format = prompt or prompt_cnf or c["main"]["prompt"] or self.default_prompt
        self.multiline_continuation_char = c["main"]["prompt_continuation"]
        self.prompt_app = None

    def close(self) -> None:
        if self.sqlexecute is not None:
            self.sqlexecute.close()

    def register_special_commands(self) -> None:
        special.register_special_command(self.change_db, "use", "\\u", "Change to a new database.", aliases=["\\u"])
        special.register_special_command(
            self.manual_reconnect,
            "connect",
            "\\r",
            "Reconnect to the database. Optional database argument.",
            aliases=["\\r"],
            case_sensitive=True,
        )
        special.register_special_command(
            self.refresh_completions, "rehash", "\\#", "Refresh auto-completions.", arg_type=ArgType.NO_QUERY, aliases=["\\#"]
        )
        special.register_special_command(
            self.change_table_format,
            "tableformat",
            "\\T",
            "Change the table format used to output results.",
            aliases=["\\T"],
            case_sensitive=True,
        )
        special.register_special_command(
            self.change_redirect_format,
            "redirectformat",
            "\\Tr",
            "Change the table format used to output redirected results.",
            aliases=["\\Tr"],
            case_sensitive=True,
        )
        special.register_special_command(
            self.disable_show_warnings,
            "nowarnings",
            "\\w",
            "Disable automatic warnings display.",
            aliases=["\\w"],
            case_sensitive=True,
        )
        special.register_special_command(
            self.enable_show_warnings,
            "warnings",
            "\\W",
            "Enable automatic warnings display.",
            aliases=["\\W"],
            case_sensitive=True,
        )
        special.register_special_command(self.execute_from_file, "source", "\\. filename", "Execute commands from file.", aliases=["\\."])
        special.register_special_command(
            self.change_prompt_format, "prompt", "\\R", "Change prompt format.", aliases=["\\R"], case_sensitive=True
        )

    def manual_reconnect(self, arg: str = "", **_) -> Generator[tuple, None, None]:
        """
        Interactive method to use for the \r command, so that the utility method
        may be cleanly used elsewhere.
        """
        if not self.reconnect(database=arg):
            yield (None, None, None, "Not connected")
        elif not arg or arg == '``':
            yield (None, None, None, None)
        else:
            yield self.change_db(arg).send(None)

    def enable_show_warnings(self, **_) -> Generator[tuple, None, None]:
        self.show_warnings = True
        msg = "Show warnings enabled."
        yield (None, None, None, msg)

    def disable_show_warnings(self, **_) -> Generator[tuple, None, None]:
        self.show_warnings = False
        msg = "Show warnings disabled."
        yield (None, None, None, msg)

    def change_table_format(self, arg: str, **_) -> Generator[tuple, None, None]:
        try:
            self.main_formatter.format_name = arg
            yield (None, None, None, f"Changed table format to {arg}")
        except ValueError:
            msg = f"Table format {arg} not recognized. Allowed formats:"
            for table_type in self.main_formatter.supported_formats:
                msg += f"\n\t{table_type}"
            yield (None, None, None, msg)

    def change_redirect_format(self, arg: str, **_) -> Generator[tuple, None, None]:
        try:
            self.redirect_formatter.format_name = arg
            yield (None, None, None, f"Changed redirect format to {arg}")
        except ValueError:
            msg = f"Redirect format {arg} not recognized. Allowed formats:"
            for table_type in self.redirect_formatter.supported_formats:
                msg += f"\n\t{table_type}"
            yield (None, None, None, msg)

    def change_db(self, arg: str, **_) -> Generator[tuple, None, None]:
        if arg.startswith("`") and arg.endswith("`"):
            arg = re.sub(r"^`(.*)`$", r"\1", arg)
            arg = re.sub(r"``", r"`", arg)

        if not arg:
            click.secho("No database selected", err=True, fg="red")
            return

        assert isinstance(self.sqlexecute, SQLExecute)

        if self.sqlexecute.dbname == arg:
            msg = f'You are already connected to database "{self.sqlexecute.dbname}" as user "{self.sqlexecute.user}"'
        else:
            self.sqlexecute.change_db(arg)
            msg = f'You are now connected to database "{self.sqlexecute.dbname}" as user "{self.sqlexecute.user}"'

        yield (
            None,
            None,
            None,
            msg,
        )

    def execute_from_file(self, arg: str, **_) -> Iterable[tuple]:
        if not arg:
            message = "Missing required argument: filename."
            return [(None, None, None, message)]
        try:
            with open(os.path.expanduser(arg)) as f:
                query = f.read()
        except IOError as e:
            return [(None, None, None, str(e))]

        if self.destructive_warning and confirm_destructive_query(query) is False:
            message = "Wise choice. Command execution stopped."
            return [(None, None, None, message)]

        assert isinstance(self.sqlexecute, SQLExecute)
        return self.sqlexecute.run(query)

    def change_prompt_format(self, arg: str, **_) -> list[tuple]:
        """
        Change the prompt format.
        """
        if not arg:
            message = "Missing required argument, format."
            return [(None, None, None, message)]

        self.prompt_format = self.get_prompt(arg)
        return [(None, None, None, f"Changed prompt format to {arg}")]

    def initialize_logging(self) -> None:
        log_file = os.path.expanduser(self.config["main"]["log_file"])
        log_level = self.config["main"]["log_level"]

        level_map = {
            "CRITICAL": logging.CRITICAL,
            "ERROR": logging.ERROR,
            "WARNING": logging.WARNING,
            "INFO": logging.INFO,
            "DEBUG": logging.DEBUG,
        }

        # Disable logging if value is NONE by switching to a no-op handler
        # Set log level to a high value so it doesn't even waste cycles getting called.
        if log_level.upper() == "NONE":
            handler: logging.Handler = logging.NullHandler()
            log_level = "CRITICAL"
        elif dir_path_exists(log_file):
            handler = logging.FileHandler(log_file)
        else:
            self.echo(f'Error: Unable to open the log file "{log_file}".', err=True, fg="red")
            return

        formatter = logging.Formatter("%(asctime)s (%(process)d/%(threadName)s) %(name)s %(levelname)s - %(message)s")

        handler.setFormatter(formatter)

        root_logger = logging.getLogger("mycli")
        root_logger.addHandler(handler)
        root_logger.setLevel(level_map[log_level.upper()])

        logging.captureWarnings(True)

        root_logger.debug("Initializing mycli logging.")
        root_logger.debug("Log file %r.", log_file)

    def read_my_cnf(self, cnf: ConfigObj, keys: list[str]) -> dict[str, Any]:
        """
        Retrieves some keys from a configuration, applies transformations, returns a new configuration.
        :param cnf: configuration to read
        :param keys: list of keys to retrieve
        :returns: tuple, with None for missing keys.
        """

        sections = ["client", "mysqld"]
        key_transformations = {
            "mysqld": {
                "socket": "default_socket",
                "port": "default_port",
                "user": "default_user",
            },
        }

        if self.login_path and self.login_path != "client":
            sections.append(self.login_path)

        if self.defaults_suffix:
            sections.extend([sect + self.defaults_suffix for sect in sections])

        configuration: dict[str, Any] = defaultdict(lambda: None)
        for key in keys:
            for section in cnf:
                if section not in sections or key not in cnf[section]:
                    continue
                new_key = key_transformations.get(section, {}).get(key) or key
                configuration[new_key] = strip_matching_quotes(cnf[section][key])

        return configuration

    def merge_ssl_with_cnf(self, ssl: dict[str, Any], cnf: dict[str, Any]) -> dict[str, Any]:
        """Merge SSL configuration dict with cnf dict"""

        merged = {}
        merged.update(ssl)
        prefix = "ssl-"
        for k, v in cnf.items():
            # skip unrelated options
            if not k.startswith(prefix):
                continue
            if v is None:
                continue
            # special case because PyMySQL argument is significantly different
            # from commandline
            if k == "ssl-verify-server-cert":
                merged["check_hostname"] = str_to_bool(v)
            else:
                # use argument name just strip "ssl-" prefix
                arg = k[len(prefix) :]
                merged[arg] = v

        return merged

    def connect(
        self,
        database: str | None = "",
        user: str | None = "",
        passwd: str | None = "",
        host: str | None = "",
        port: str | int | None = "",
        socket: str | None = "",
        charset: str | None = "",
        local_infile: bool = False,
        ssl: dict[str, Any] | None = None,
        ssh_user: str | None = "",
        ssh_host: str | None = "",
        ssh_port: int = 22,
        ssh_password: str | None = "",
        ssh_key_filename: str | None = "",
        init_command: str | None = "",
        password_file: str | None = "",
    ) -> None:
        cnf = {
            "database": None,
            "user": None,
            "password": None,
            "host": None,
            "port": None,
            "socket": None,
            "default_socket": None,
            "default-character-set": None,
            "local-infile": None,
            "loose-local-infile": None,
            "ssl-ca": None,
            "ssl-cert": None,
            "ssl-key": None,
            "ssl-cipher": None,
            "ssl-verify-server-cert": None,
        }

        cnf = self.read_my_cnf(self.my_cnf, list(cnf.keys()))

        # Fall back to config values only if user did not specify a value.
        database = database or cnf["database"]
        user = user or cnf["user"] or os.getenv("USER")
        host = host or cnf["host"]
        port = port or cnf["port"]
        ssl_config: dict[str, Any] = ssl or {}

        int_port = port and int(port)
        if not int_port:
            int_port = 3306
            if not host or host == "localhost":
                socket = socket or cnf["socket"] or cnf["default_socket"] or guess_socket_location()

        passwd = passwd if isinstance(passwd, str) else cnf["password"]
        charset = charset or cnf["default-character-set"] or "utf8"

        # Favor whichever local_infile option is set.
        use_local_infile = False
        for local_infile_option in (local_infile, cnf["local-infile"], cnf["loose-local-infile"], False):
            try:
                use_local_infile = str_to_bool(local_infile_option or '')
                break
            except (TypeError, ValueError):
                pass

        ssl_config_or_none: dict[str, Any] | None = self.merge_ssl_with_cnf(ssl_config, cnf)
        # prune lone check_hostname=False
        if not any(v for v in ssl_config.values()):
            ssl_config_or_none = None

        # if the passwd is not specified try to set it using the password_file option
        password_from_file = self.get_password_from_file(password_file)
        passwd = passwd if isinstance(passwd, str) else password_from_file
        passwd = '' if passwd is None else passwd

        # Connect to the database.

        def _connect() -> None:
            try:
                self.sqlexecute = SQLExecute(
                    database,
                    user,
                    passwd,
                    host,
                    int_port,
                    socket,
                    charset,
                    use_local_infile,
                    ssl_config_or_none,
                    ssh_user,
                    ssh_host,
                    int(ssh_port) if ssh_port else None,
                    ssh_password,
                    ssh_key_filename,
                    init_command,
                )
            except pymysql.OperationalError as e1:
                if e1.args[0] == ERROR_CODE_ACCESS_DENIED:
                    if password_from_file is not None:
                        new_passwd = password_from_file
                    else:
                        new_passwd = click.prompt(
                            f"Password for {user}", hide_input=True, show_default=False, default='', type=str, err=True
                        )
                    self.sqlexecute = SQLExecute(
                        database,
                        user,
                        new_passwd,
                        host,
                        int_port,
                        socket,
                        charset,
                        use_local_infile,
                        ssl_config_or_none,
                        ssh_user,
                        ssh_host,
                        int(ssh_port) if ssh_port else None,
                        ssh_password,
                        ssh_key_filename,
                        init_command,
                    )
                elif e1.args[0] == HANDSHAKE_ERROR and ssl is not None and ssl.get("mode", None) == "auto":
                    try:
                        self.sqlexecute = SQLExecute(
                            database,
                            user,
                            passwd,
                            host,
                            int_port,
                            socket,
                            charset,
                            use_local_infile,
                            None,
                            ssh_user,
                            ssh_host,
                            int(ssh_port) if ssh_port else None,
                            ssh_password,
                            ssh_key_filename,
                            init_command,
                        )
                    except pymysql.OperationalError as e2:
                        if e2.args[0] == ERROR_CODE_ACCESS_DENIED:
                            if password_from_file is not None:
                                new_passwd = password_from_file
                            else:
                                new_passwd = click.prompt(
                                    f"Password for {user}", hide_input=True, show_default=False, default='', type=str, err=True
                                )
                            self.sqlexecute = SQLExecute(
                                database,
                                user,
                                new_passwd,
                                host,
                                int_port,
                                socket,
                                charset,
                                use_local_infile,
                                None,
                                ssh_user,
                                ssh_host,
                                int(ssh_port) if ssh_port else None,
                                ssh_password,
                                ssh_key_filename,
                                init_command,
                            )
                        else:
                            raise e2
                else:
                    raise e1

        try:
            if not WIN and socket:
                socket_owner = getpwuid(os.stat(socket).st_uid).pw_name
                self.echo(f"Connecting to socket {socket}, owned by user {socket_owner}", err=True)
                try:
                    _connect()
                except pymysql.OperationalError as e:
                    # These are "Can't open socket" and 2x "Can't connect"
                    if [code for code in (2001, 2002, 2003) if code == e.args[0]]:
                        self.logger.debug("Database connection failed: %r.", e)
                        self.logger.error("traceback: %r", traceback.format_exc())
                        self.logger.debug("Retrying over TCP/IP")
                        self.echo(f"Failed to connect to local MySQL server through socket '{socket}':")
                        self.echo(str(e), err=True)
                        self.echo("Retrying over TCP/IP", err=True)

                        # Else fall back to TCP/IP localhost
                        socket = ""
                        host = "localhost"
                        port = 3306
                        _connect()
                    else:
                        raise e
            else:
                host = host or "localhost"
                port = port or 3306

                # Bad ports give particularly daft error messages
                try:
                    port = int(port)
                except ValueError:
                    self.echo(f"Error: Invalid port number: '{port}'.", err=True, fg="red")
                    sys.exit(1)

                _connect()
        except Exception as e:  # Connecting to a database could fail.
            self.logger.debug("Database connection failed: %r.", e)
            self.logger.error("traceback: %r", traceback.format_exc())
            self.echo(str(e), err=True, fg="red")
            sys.exit(1)

    def get_password_from_file(self, password_file: str | None) -> str | None:
        if not password_file:
            return None
        try:
            with open(password_file) as fp:
                password = fp.readline().strip()
                return password
        except FileNotFoundError:
            click.secho(f"Password file '{password_file}' not found", err=True, fg="red")
            sys.exit(1)
        except PermissionError:
            click.secho(f"Permission denied reading password file '{password_file}'", err=True, fg="red")
            sys.exit(1)
        except IsADirectoryError:
            click.secho(f"Path '{password_file}' is a directory, not a file", err=True, fg="red")
            sys.exit(1)
        except Exception as e:
            click.secho(f"Error reading password file '{password_file}': {str(e)}", err=True, fg="red")
            sys.exit(1)

    def handle_editor_command(self, text: str) -> str:
        r"""Editor command is any query that is prefixed or suffixed by a '\e'.
        The reason for a while loop is because a user might edit a query
        multiple times. For eg:

        "select * from \e"<enter> to edit it in vim, then come
        back to the prompt with the edited query "select * from
        blah where q = 'abc'\e" to edit it again.
        :param text: Document
        :return: Document

        """

        while special.editor_command(text):
            filename = special.get_filename(text)
            query = special.get_editor_query(text) or self.get_last_query()
            sql, message = special.open_external_editor(filename=filename, sql=query)
            if message:
                # Something went wrong. Raise an exception and bail.
                raise RuntimeError(message)
            while True:
                try:
                    assert isinstance(self.prompt_app, PromptSession)
                    text = self.prompt_app.prompt(default=sql)
                    break
                except KeyboardInterrupt:
                    sql = ""

            continue
        return text

    def handle_clip_command(self, text: str) -> bool:
        r"""A clip command is any query that is prefixed or suffixed by a
        '\clip'.

        :param text: Document
        :return: Boolean

        """

        if special.clip_command(text):
            query = special.get_clip_query(text) or self.get_last_query()
            message = special.copy_query_to_clipboard(sql=query)
            if message:
                raise RuntimeError(message)
            return True
        return False

    def handle_prettify_binding(self, text: str) -> str:
        try:
            statements = sqlglot.parse(text, read="mysql")
        except Exception:
            statements = []
        if len(statements) == 1 and statements[0]:
            pretty_text = statements[0].sql(pretty=True, pad=4, dialect="mysql")
        else:
            pretty_text = ""
            self.toolbar_error_message = "Prettify failed to parse statement"
        if len(pretty_text) > 0:
            pretty_text = pretty_text + ";"
        return pretty_text

    def handle_unprettify_binding(self, text: str) -> str:
        try:
            statements = sqlglot.parse(text, read="mysql")
        except Exception:
            statements = []
        if len(statements) == 1 and statements[0]:
            unpretty_text = statements[0].sql(pretty=False, dialect="mysql")
        else:
            unpretty_text = ""
            self.toolbar_error_message = "Unprettify failed to parse statement"
        if len(unpretty_text) > 0:
            unpretty_text = unpretty_text + ";"
        return unpretty_text

    def run_cli(self) -> None:
        iterations = 0
        sqlexecute = self.sqlexecute
        assert isinstance(sqlexecute, SQLExecute)
        logger = self.logger
        self.configure_pager()

        if self.smart_completion:
            self.refresh_completions()

        history_file = os.path.expanduser(os.environ.get("MYCLI_HISTFILE", "~/.mycli-history"))
        if dir_path_exists(history_file):
            history = FileHistoryWithTimestamp(history_file)
        else:
            history = None
            self.echo(
                f'Error: Unable to open the history file "{history_file}". Your query history will not be saved.',
                err=True,
                fg="red",
            )

        key_bindings = mycli_bindings(self)

        if not self.less_chatty:
            print(sqlexecute.server_info)
            print("mycli", __version__)
            print(SUPPORT_INFO)
            print("Thanks to the contributor -", thanks_picker())

        def get_message() -> ANSI:
            prompt = self.get_prompt(self.prompt_format)
            if self.prompt_format == self.default_prompt and len(prompt) > self.max_len_prompt:
                prompt = self.get_prompt(self.default_prompt_splitln)
            prompt = prompt.replace("\\x1b", "\x1b")
            return ANSI(prompt)

        def get_continuation(width: int, _two: int, _three: int) -> AnyFormattedText:
            if self.multiline_continuation_char == "":
                continuation = ""
            elif self.multiline_continuation_char:
                left_padding = width - len(self.multiline_continuation_char)
                continuation = " " * max((left_padding - 1), 0) + self.multiline_continuation_char + " "
            else:
                continuation = " "
            return [("class:continuation", continuation)]

        def show_suggestion_tip() -> bool:
            return iterations < 2

        # Keep track of whether or not the query is mutating. In case
        # of a multi-statement query, the overall query is considered
        # mutating if any one of the component statements is mutating
        mutating = False

        def output_res(res: Generator[tuple], start: float) -> None:
            nonlocal mutating
            result_count = 0
            for title, cur, headers, status in res:
                logger.debug("headers: %r", headers)
                logger.debug("rows: %r", cur)
                logger.debug("status: %r", status)
                threshold = 1000
                if is_select(status) and cur and cur.rowcount > threshold:
                    self.echo(
                        f"The result set has more than {threshold} rows.",
                        fg="red",
                    )
                    if not confirm("Do you want to continue?"):
                        self.echo("Aborted!", err=True, fg="red")
                        break

                if self.auto_vertical_output:
                    if self.prompt_app is not None:
                        max_width = self.prompt_app.output.get_size().columns
                    else:
                        max_width = DEFAULT_WIDTH
                else:
                    max_width = None

                formatted = self.format_output(
                    title,
                    cur,
                    headers,
                    special.is_expanded_output(),
                    special.is_redirected(),
                    self.null_string,
                    max_width,
                )

                t = time() - start
                try:
                    if result_count > 0:
                        self.echo("")
                    try:
                        self.output(formatted, status)
                    except KeyboardInterrupt:
                        pass
                    if self.beep_after_seconds > 0 and t >= self.beep_after_seconds:
                        self.bell()
                    if special.is_timing_enabled():
                        self.echo(f"Time: {t:0.03f}s")
                except KeyboardInterrupt:
                    pass

                start = time()
                result_count += 1
                mutating = mutating or is_mutating(status)

                # get and display warnings if enabled
                if self.show_warnings and isinstance(cur, Cursor) and cur.warning_count > 0:
                    warnings = sqlexecute.run("SHOW WARNINGS")
                    for title, cur, headers, status in warnings:
                        formatted = self.format_output(
                            title,
                            cur,
                            headers,
                            special.is_expanded_output(),
                            special.is_redirected(),
                            self.null_string,
                            max_width,
                        )
                        self.echo("")
                        self.output(formatted, status)

        def one_iteration(text: str | None = None) -> None:
            if text is None:
                try:
                    assert self.prompt_app is not None
                    text = self.prompt_app.prompt()
                except KeyboardInterrupt:
                    return

                special.set_expanded_output(False)
                special.set_forced_horizontal_output(False)

                try:
                    text = self.handle_editor_command(text)
                except RuntimeError as e:
                    logger.error("sql: %r, error: %r", text, e)
                    logger.error("traceback: %r", traceback.format_exc())
                    self.echo(str(e), err=True, fg="red")
                    return

                try:
                    if self.handle_clip_command(text):
                        return
                except RuntimeError as e:
                    logger.error("sql: %r, error: %r", text, e)
                    logger.error("traceback: %r", traceback.format_exc())
                    self.echo(str(e), err=True, fg="red")
                    return
                # LLM command support
                while special.is_llm_command(text):
                    start = time()
                    try:
                        assert sqlexecute.conn is not None
                        cur = sqlexecute.conn.cursor()
                        context, sql, duration = special.handle_llm(text, cur)
                        if context:
                            click.echo("LLM Response:")
                            click.echo(context)
                            click.echo("---")
                        if special.is_timing_enabled():
                            click.echo(f"Time: {duration:.2f} seconds")
                        text = self.prompt_app.prompt(default=sql or '')
                    except KeyboardInterrupt:
                        return
                    except special.FinishIteration as e:
                        if e.results:
                            return output_res(e.results, start)
                        else:
                            return None
                    except RuntimeError as e:
                        logger.error("sql: %r, error: %r", text, e)
                        logger.error("traceback: %r", traceback.format_exc())
                        self.echo(str(e), err=True, fg="red")
                        return

            text = text.strip()

            if not text:
                return

            if is_redirect_command(text):
                sql_part, command_part, file_operator_part, file_part = get_redirect_components(text)
                text = sql_part or ''
                try:
                    special.set_redirect(command_part, file_operator_part, file_part)
                except (FileNotFoundError, OSError, RuntimeError) as e:
                    logger.error("sql: %r, error: %r", text, e)
                    logger.error("traceback: %r", traceback.format_exc())
                    self.echo(str(e), err=True, fg="red")
                    return

            if self.destructive_warning:
                destroy = confirm_destructive_query(text)
                if destroy is None:
                    pass  # Query was not destructive. Nothing to do here.
                elif destroy is True:
                    self.echo("Your call!")
                else:
                    self.echo("Wise choice!")
                    return
            else:
                destroy = True

            try:
                logger.debug("sql: %r", text)

                special.write_tee(self.get_prompt(self.prompt_format) + text)
                if self.logfile:
                    self.logfile.write(f"\n# {datetime.now()}\n")
                    self.logfile.write(text)
                    self.logfile.write("\n")

                successful = False
                start = time()
                res = sqlexecute.run(text)
                self.main_formatter.query = text
                self.redirect_formatter.query = text
                successful = True
                output_res(res, start)
                special.unset_once_if_written(self.post_redirect_command)
                special.flush_pipe_once_if_written(self.post_redirect_command)
            except pymysql.err.InterfaceError:
                # attempt to reconnect
                if not self.reconnect():
                    return
                one_iteration(text)
                return  # OK to just return, cuz the recursion call runs to the end.
            except EOFError as e:
                raise e
            except KeyboardInterrupt:
                # get last connection id
                connection_id_to_kill = sqlexecute.connection_id or 0
                # some mysql compatible databases may not implemente connection_id()
                if connection_id_to_kill > 0:
                    logger.debug("connection id to kill: %r", connection_id_to_kill)
                    # Restart connection to the database
                    sqlexecute.connect()
                    try:
                        for _title, _cur, _headers, status in sqlexecute.run(f"kill {connection_id_to_kill}"):
                            status_str = str(status).lower()
                            if status_str.find("ok") > -1:
                                logger.debug("cancelled query, connection id: %r, sql: %r", connection_id_to_kill, text)
                                self.echo(f"Cancelled query id: {connection_id_to_kill}", err=True, fg="blue")
                            else:
                                logger.debug(
                                    "Failed to confirm query cancellation, connection id: %r, sql: %r",
                                    connection_id_to_kill,
                                    text,
                                )
                                self.echo(f"Failed to confirm query cancellation, id: {connection_id_to_kill}", err=True, fg="red")
                    except Exception as e:
                        self.echo(f"Encountered error while cancelling query: {e}", err=True, fg="red")
                else:
                    logger.debug("Did not get a connection id, skip cancelling query")
                    self.echo("Did not get a connection id, skip cancelling query", err=True, fg="red")
            except NotImplementedError:
                self.echo("Not Yet Implemented.", fg="yellow")
            except pymysql.OperationalError as e1:
                logger.debug("Exception: %r", e1)
                if e1.args[0] in (2003, 2006, 2013):
                    # attempt to reconnect
                    if not self.reconnect():
                        return
                    one_iteration(text)
                    return  # OK to just return, cuz the recursion call runs to the end.
                else:
                    logger.error("sql: %r, error: %r", text, e1)
                    logger.error("traceback: %r", traceback.format_exc())
                    self.echo(str(e1), err=True, fg="red")
            except Exception as e:
                logger.error("sql: %r, error: %r", text, e)
                logger.error("traceback: %r", traceback.format_exc())
                self.echo(str(e), err=True, fg="red")
            else:
                if is_dropping_database(text, sqlexecute.dbname):
                    sqlexecute.dbname = None
                    sqlexecute.connect()

                # Refresh the table names and column names if necessary.
                if need_completion_refresh(text):
                    self.refresh_completions(reset=need_completion_reset(text))
            finally:
                if self.logfile is False:
                    self.echo("Warning: This query was not logged.", err=True, fg="red")
            query = Query(text, successful, mutating)
            self.query_history.append(query)

        get_toolbar_tokens = create_toolbar_tokens_func(self, show_suggestion_tip)
        if self.wider_completion_menu:
            complete_style = CompleteStyle.MULTI_COLUMN
        else:
            complete_style = CompleteStyle.COLUMN

        with self._completer_lock:
            if self.key_bindings == "vi":
                editing_mode = EditingMode.VI
            else:
                editing_mode = EditingMode.EMACS

            self.prompt_app = PromptSession(
                lexer=PygmentsLexer(MyCliLexer),
                reserve_space_for_menu=self.get_reserved_space(),
                message=get_message,
                prompt_continuation=get_continuation,
                bottom_toolbar=get_toolbar_tokens,
                complete_style=complete_style,
                input_processors=[
                    ConditionalProcessor(
                        processor=HighlightMatchingBracketProcessor(chars="[](){}"), filter=HasFocus(DEFAULT_BUFFER) & ~IsDone()
                    )
                ],
                tempfile_suffix=".sql",
                completer=DynamicCompleter(lambda: self.completer),
                history=history,
                auto_suggest=AutoSuggestFromHistory(),
                complete_while_typing=True,
                multiline=cli_is_multiline(self),
                style=style_factory(self.syntax_style, self.cli_style),
                include_default_pygments_style=False,
                key_bindings=key_bindings,
                enable_open_in_editor=True,
                enable_system_prompt=True,
                enable_suspend=True,
                editing_mode=editing_mode,
                search_ignore_case=True,
            )

        try:
            while True:
                one_iteration()
                iterations += 1
        except EOFError:
            special.close_tee()
            if not self.less_chatty:
                self.echo("Goodbye!")

    def reconnect(self, database: str = "") -> bool:
        """
        Attempt to reconnect to the server. Return True if successful,
        False if unsuccessful.

        The "database" argument is used only to improve messages.
        """
        assert self.sqlexecute is not None
        assert self.sqlexecute.conn is not None

        # First pass with ping(reconnect=False) and minimal feedback levels.  This definitely
        # works as expected, and is a good idea especially when "connect" was used as a
        # synonym for "use".
        try:
            self.sqlexecute.conn.ping(reconnect=False)
            if not database:
                self.echo("Already connected.", fg="yellow")
            return True
        except pymysql.err.Error:
            pass

        # Second pass with ping(reconnect=True).  It is not demonstrated that this pass ever
        # gives the benefit it is looking for, _ie_ preserves session state.  We need to test
        # this with connection pooling.
        try:
            old_connection_id = self.sqlexecute.connection_id
            self.logger.debug("Attempting to reconnect.")
            self.echo("Reconnecting...", fg="yellow")
            self.sqlexecute.conn.ping(reconnect=True)
            self.logger.debug("Reconnected successfully.")
            self.echo("Reconnected successfully.", fg="yellow")
            self.sqlexecute.reset_connection_id()
            if old_connection_id != self.sqlexecute.connection_id:
                self.echo("Any session state was reset.", fg="red")
            return True
        except pymysql.err.Error:
            pass

        # Third pass with sqlexecute.connect() should always work, but always resets session state.
        try:
            self.logger.debug("Creating new connection")
            self.echo("Creating new connection...", fg="yellow")
            self.sqlexecute.connect()
            self.logger.debug("New connection created successfully.")
            self.echo("New connection created successfully.", fg="yellow")
            self.echo("Any session state was reset.", fg="red")
            return True
        except pymysql.OperationalError as e:
            self.logger.debug("Reconnect failed. e: %r", e)
            self.echo(str(e), err=True, fg="red")
            return False

    def log_output(self, output: str) -> None:
        """Log the output in the audit log, if it's enabled."""
        if isinstance(self.logfile, TextIOWrapper):
            click.echo(output, file=self.logfile)

    def echo(self, s: str, **kwargs) -> None:
        """Print a message to stdout.

        The message will be logged in the audit log, if enabled.

        All keyword arguments are passed to click.echo().

        """
        self.log_output(s)
        click.secho(s, **kwargs)

    def bell(self) -> None:
        """Print a bell on the stderr."""
        click.secho("\a", err=True, nl=False)

    def get_output_margin(self, status: str | None = None) -> int:
        """Get the output margin (number of rows for the prompt, footer and
        timing message."""
        margin = self.get_reserved_space() + self.get_prompt(self.prompt_format).count("\n") + 1
        if special.is_timing_enabled():
            margin += 1
        if status:
            margin += 1 + status.count("\n")

        return margin

    def output(self, output: itertools.chain[str], status: str | None = None) -> None:
        """Output text to stdout or a pager command.

        The status text is not outputted to pager or files.

        The message will be logged in the audit log, if enabled. The
        message will be written to the tee file, if enabled. The
        message will be written to the output file, if enabled.

        """
        if output:
            if self.prompt_app is not None:
                size = self.prompt_app.output.get_size()
                size_columns = size.columns
                size_rows = size.rows
            else:
                size_columns = DEFAULT_WIDTH
                size_rows = DEFAULT_HEIGHT

            margin = self.get_output_margin(status)

            fits = True
            buf = []
            output_via_pager = self.explicit_pager and special.is_pager_enabled()
            for i, line in enumerate(output, 1):
                self.log_output(line)
                special.write_tee(line)
                special.write_once(line)
                special.write_pipe_once(line)

                if special.is_redirected():
                    pass
                elif fits or output_via_pager:
                    # buffering
                    buf.append(line)
                    if len(line) > size_columns or i > (size_rows - margin):
                        fits = False
                        if not self.explicit_pager and special.is_pager_enabled():
                            # doesn't fit, use pager
                            output_via_pager = True

                        if not output_via_pager:
                            # doesn't fit, flush buffer
                            for buf_line in buf:
                                click.secho(buf_line)
                            buf = []
                else:
                    click.secho(line)

            if buf:
                if output_via_pager:

                    def newlinewrapper(text: list[str]) -> Generator[str, None, None]:
                        for line in text:
                            yield line + "\n"

                    click.echo_via_pager(newlinewrapper(buf))
                else:
                    for line in buf:
                        click.secho(line)

        if status:
            self.log_output(status)
            click.secho(status)

    def configure_pager(self) -> None:
        # Provide sane defaults for less if they are empty.
        if not os.environ.get("LESS"):
            os.environ["LESS"] = "-RXF"

        cnf = self.read_my_cnf(self.my_cnf, ["pager", "skip-pager"])
        cnf_pager = cnf["pager"] or self.config["main"]["pager"]

        # help Windows users who haven't edited the default myclirc
        if WIN and cnf_pager == 'less' and not shutil.which(cnf_pager):
            cnf_pager = 'more'

        if cnf_pager:
            special.set_pager(cnf_pager)
            self.explicit_pager = True
        else:
            self.explicit_pager = False

        if cnf["skip-pager"] or not self.config["main"].as_bool("enable_pager"):
            special.disable_pager()

    def refresh_completions(self, reset: bool = False) -> list[tuple]:
        if reset:
            with self._completer_lock:
                self.completer.reset_completions()
        assert self.sqlexecute is not None
        self.completion_refresher.refresh(
            self.sqlexecute,
            self._on_completions_refreshed,
            {
                "smart_completion": self.smart_completion,
                "supported_formats": self.main_formatter.supported_formats,
                "keyword_casing": self.completer.keyword_casing,
            },
        )

        return [(None, None, None, "Auto-completion refresh started in the background.")]

    def _on_completions_refreshed(self, new_completer: SQLCompleter) -> None:
        """Swap the completer object in cli with the newly created completer."""
        with self._completer_lock:
            self.completer = new_completer

        if self.prompt_app:
            # After refreshing, redraw the CLI to clear the statusbar
            # "Refreshing completions..." indicator
            self.prompt_app.app.invalidate()

    def get_completions(self, text: str, cursor_position: int) -> Iterable[Completion]:
        with self._completer_lock:
            return self.completer.get_completions(Document(text=text, cursor_position=cursor_position), None)

    def get_prompt(self, string: str) -> str:
        sqlexecute = self.sqlexecute
        assert sqlexecute is not None
        assert sqlexecute.server_info is not None
        assert sqlexecute.server_info.species is not None
        if self.login_path and self.login_path_as_host:
            prompt_host = self.login_path
        elif sqlexecute.host is not None:
            prompt_host = sqlexecute.host
        else:
            prompt_host = "localhost"
        now = datetime.now()
        string = string.replace("\\u", sqlexecute.user or "(none)")
        string = string.replace("\\h", prompt_host or "(none)")
        string = string.replace("\\d", sqlexecute.dbname or "(none)")
        string = string.replace("\\t", sqlexecute.server_info.species.name)
        string = string.replace("\\n", "\n")
        string = string.replace("\\D", now.strftime("%a %b %d %H:%M:%S %Y"))
        string = string.replace("\\m", now.strftime("%M"))
        string = string.replace("\\P", now.strftime("%p"))
        string = string.replace("\\R", now.strftime("%H"))
        string = string.replace("\\r", now.strftime("%I"))
        string = string.replace("\\s", now.strftime("%S"))
        string = string.replace("\\p", str(sqlexecute.port))
        string = string.replace("\\A", self.dsn_alias or "(none)")
        string = string.replace("\\_", " ")
        return string

    def run_query(self, query: str, new_line: bool = True) -> None:
        """Runs *query*."""
        assert self.sqlexecute is not None
        results = self.sqlexecute.run(query)
        for result in results:
            title, cur, headers, status = result
            self.main_formatter.query = query
            self.redirect_formatter.query = query
            output = self.format_output(
                title,
                cur,
                headers,
                special.is_expanded_output(),
                special.is_redirected(),
                self.null_string,
            )
            for line in output:
                click.echo(line, nl=new_line)

            # get and display warnings if enabled
            if self.show_warnings and isinstance(cur, Cursor) and cur.warning_count > 0:
                warnings = self.sqlexecute.run("SHOW WARNINGS")
                for title, cur, headers, _ in warnings:
                    output = self.format_output(
                        title,
                        cur,
                        headers,
                        special.is_expanded_output(),
                        special.is_redirected(),
                        self.null_string,
                    )
                    for line in output:
                        click.echo(line, nl=new_line)

    def format_output(
        self,
        title: str | None,
        cur: Cursor | list[tuple] | None,
        headers: list[str] | None,
        expanded: bool = False,
        is_redirected: bool = False,
        null_string: str | None = None,
        max_width: int | None = None,
    ) -> itertools.chain[str]:
        if is_redirected:
            use_formatter = self.redirect_formatter
        else:
            use_formatter = self.main_formatter

        expanded = expanded or use_formatter.format_name == "vertical"
        output: itertools.chain[str] = itertools.chain()

        output_kwargs = {
            "dialect": "unix",
            "disable_numparse": True,
            "preserve_whitespace": True,
            "style": self.output_style,
        }
        default_kwargs = use_formatter._output_formats[use_formatter.format_name].formatter_args

        if null_string is not None and default_kwargs.get('missing_value') == DEFAULT_MISSING_VALUE:
            output_kwargs['missing_value'] = null_string

        if use_formatter.format_name not in sql_format.supported_formats:
            output_kwargs["preprocessors"] = (preprocessors.align_decimals,)

        if title:  # Only print the title if it's not None.
            output = itertools.chain(output, [title])

        if headers or (cur and title):
            column_types = None
            if isinstance(cur, Cursor):

                def get_col_type(col) -> type:
                    col_type = FIELD_TYPES.get(col[1], str)
                    return col_type if type(col_type) is type else str

                column_types = [get_col_type(tup) for tup in cur.description]

            if max_width is not None and isinstance(cur, Cursor):
                cur = list(cur)

            formatted = use_formatter.format_output(
                cur,
                headers,
                format_name="vertical" if expanded else None,
                column_types=column_types,
                **output_kwargs,
            )

            if isinstance(formatted, str):
                formatted = formatted.splitlines()
            formatted = iter(formatted)

            if not expanded and max_width and headers and cur:
                first_line = next(formatted)
                if len(strip_ansi(first_line)) > max_width:
                    formatted = use_formatter.format_output(
                        cur,
                        headers,
                        format_name="vertical",
                        column_types=column_types,
                        **output_kwargs,
                    )
                    if isinstance(formatted, str):
                        formatted = iter(formatted.splitlines())
                else:
                    formatted = itertools.chain([first_line], formatted)

            output = itertools.chain(output, formatted)

        return output

    def get_reserved_space(self) -> int:
        """Get the number of lines to reserve for the completion menu."""
        reserved_space_ratio = 0.45
        max_reserved_space = 8
        _, height = shutil.get_terminal_size()
        return min(int(round(height * reserved_space_ratio)), max_reserved_space)

    def get_last_query(self) -> str | None:
        """Get the last query executed or None."""
        return self.query_history[-1][0] if self.query_history else None


@click.command()
@click.option("-h", "--host", envvar="MYSQL_HOST", help="Host address of the database.")
@click.option("-P", "--port", envvar="MYSQL_TCP_PORT", type=int, help="Port number to use for connection. Honors $MYSQL_TCP_PORT.")
@click.option("-u", "--user", help="User name to connect to the database.")
@click.option("-S", "--socket", envvar="MYSQL_UNIX_PORT", help="The socket file to use for connection.")
@click.option("-p", "--password", "password", envvar="MYSQL_PWD", type=str, help="Password to connect to the database.")
@click.option("--pass", "password", envvar="MYSQL_PWD", type=str, help="Password to connect to the database.")
@click.option("--ssh-user", help="User name to connect to ssh server.")
@click.option("--ssh-host", help="Host name to connect to ssh server.")
@click.option("--ssh-port", default=22, help="Port to connect to ssh server.")
@click.option("--ssh-password", help="Password to connect to ssh server.")
@click.option("--ssh-key-filename", help="Private key filename (identify file) for the ssh connection.")
@click.option("--ssh-config-path", help="Path to ssh configuration.", default=os.path.expanduser("~") + "/.ssh/config")
@click.option("--ssh-config-host", help="Host to connect to ssh server reading from ssh configuration.")
@click.option(
    "--ssl-mode",
    "ssl_mode",
    help="Set desired SSL behavior. auto=preferred, on=required, off=off.",
    type=click.Choice(["auto", "on", "off"]),
)
@click.option("--ssl/--no-ssl", "ssl_enable", default=None, help="Enable SSL for connection (automatically enabled with other flags).")
@click.option("--ssl-ca", help="CA file in PEM format.", type=click.Path(exists=True))
@click.option("--ssl-capath", help="CA directory.")
@click.option("--ssl-cert", help="X509 cert in PEM format.", type=click.Path(exists=True))
@click.option("--ssl-key", help="X509 key in PEM format.", type=click.Path(exists=True))
@click.option("--ssl-cipher", help="SSL cipher to use.")
@click.option(
    "--tls-version",
    type=click.Choice(["TLSv1", "TLSv1.1", "TLSv1.2", "TLSv1.3"], case_sensitive=False),
    help="TLS protocol version for secure connection.",
)
@click.option(
    "--ssl-verify-server-cert",
    is_flag=True,
    help=("""Verify server's "Common Name" in its cert against hostname used when connecting. This option is disabled by default."""),
)
@click.version_option(__version__, "-V", "--version", help="Output mycli's version.")
@click.option("-v", "--verbose", is_flag=True, help="Verbose output.")
@click.option("-D", "--database", "dbname", help="Database to use.")
@click.option("-d", "--dsn", default="", envvar="DSN", help="Use DSN configured into the [alias_dsn] section of myclirc file.")
@click.option("--list-dsn", "list_dsn", is_flag=True, help="list of DSN configured into the [alias_dsn] section of myclirc file.")
@click.option("--list-ssh-config", "list_ssh_config", is_flag=True, help="list ssh configurations in the ssh config (requires paramiko).")
@click.option("-R", "--prompt", "prompt", help=f'Prompt format (Default: "{MyCli.default_prompt}").')
@click.option("-l", "--logfile", type=click.File(mode="a", encoding="utf-8"), help="Log every query and its results to a file.")
@click.option("--defaults-group-suffix", type=str, help="Read MySQL config groups with the specified suffix.")
@click.option("--defaults-file", type=click.Path(), help="Only read MySQL options from the given file.")
@click.option("--myclirc", type=click.Path(), default="~/.myclirc", help="Location of myclirc file.")
@click.option(
    "--auto-vertical-output",
    is_flag=True,
    help="Automatically switch to vertical output mode if the result is wider than the terminal width.",
)
@click.option(
    "--show-warnings/--no-show-warnings", "show_warnings", is_flag=True, help="Automatically show warnings after executing a SQL statement."
)
@click.option("-t", "--table", is_flag=True, help="Display batch output in table format.")
@click.option("--csv", is_flag=True, help="Display batch output in CSV format.")
@click.option("--warn/--no-warn", default=None, help="Warn before running a destructive query.")
@click.option("--local-infile", type=bool, help="Enable/disable LOAD DATA LOCAL INFILE.")
@click.option("-g", "--login-path", type=str, help="Read this path from the login file.")
@click.option("-e", "--execute", type=str, help="Execute command and quit.")
@click.option("--init-command", type=str, help="SQL statement to execute after connecting.")
@click.option("--charset", type=str, help="Character set for MySQL session.")
@click.option(
    "--password-file", type=click.Path(), help="File or FIFO path containing the password to connect to the db if not specified otherwise."
)
@click.argument("database", default="", nargs=1)
def cli(
    database: str,
    user: str | None,
    host: str | None,
    port: int | None,
    socket: str | None,
    password: str | None,
    dbname: str | None,
    verbose: bool,
    prompt: str | None,
    logfile: TextIOWrapper | None,
    defaults_group_suffix: str | None,
    defaults_file: str | None,
    login_path: str | None,
    auto_vertical_output: bool,
    show_warnings: bool,
    local_infile: bool,
    ssl_mode: str | None,
    ssl_enable: bool,
    ssl_ca: str | None,
    ssl_capath: str | None,
    ssl_cert: str | None,
    ssl_key: str | None,
    ssl_cipher: str | None,
    tls_version: str | None,
    ssl_verify_server_cert: bool,
    table: bool,
    csv: bool,
    warn: bool | None,
    execute: str | None,
    myclirc: str,
    dsn: str,
    list_dsn: str | None,
    ssh_user: str | None,
    ssh_host: str | None,
    ssh_port: int,
    ssh_password: str | None,
    ssh_key_filename: str | None,
    list_ssh_config: bool,
    ssh_config_path: str,
    ssh_config_host: str | None,
    init_command: str | None,
    charset: str | None,
    password_file: str | None,
) -> None:
    """A MySQL terminal client with auto-completion and syntax highlighting.

    \b
    Examples:
      - mycli my_database
      - mycli -u my_user -h my_host.com my_database
      - mycli mysql://my_user@my_host.com:3306/my_database

    """
    mycli = MyCli(
        prompt=prompt,
        logfile=logfile,
        defaults_suffix=defaults_group_suffix,
        defaults_file=defaults_file,
        login_path=login_path,
        auto_vertical_output=auto_vertical_output,
        warn=warn,
        myclirc=myclirc,
    )

    if ssl_enable is not None:
        click.secho(
            "Warning: The --ssl/--no-ssl CLI options are deprecated and will be removed in a future release. "
            "Please use the ssl_mode config or --ssl-mode CLI options instead.",
            err=True,
            fg="yellow",
        )

    if list_dsn:
        try:
            alias_dsn = mycli.config["alias_dsn"]
        except KeyError:
            click.secho("Invalid DSNs found in the config file. Please check the \"[alias_dsn]\" section in myclirc.", err=True, fg="red")
            sys.exit(1)
        except Exception as e:
            click.secho(str(e), err=True, fg="red")
            sys.exit(1)
        for alias, value in alias_dsn.items():
            if verbose:
                click.secho(f"{alias} : {value}")
            else:
                click.secho(alias)
        sys.exit(0)
    if list_ssh_config:
        ssh_config = read_ssh_config(ssh_config_path)
        for host in ssh_config.get_hostnames():
            if verbose:
                host_config = ssh_config.lookup(host)
                click.secho(f"{host} : {host_config.get('hostname')}")
            else:
                click.secho(host)
        sys.exit(0)
    # Choose which ever one has a valid value.
    database = dbname or database

    dsn_uri = None

    # Treat the database argument as a DSN alias only if it matches a configured alias
    if (
        database
        and "://" not in database
        and not any([user, password, host, port, login_path])
        and database in mycli.config.get("alias_dsn", {})
    ):
        dsn, database = database, ""

    if database and "://" in database:
        dsn_uri, database = database, ""

    if dsn:
        try:
            dsn_uri = mycli.config["alias_dsn"][dsn]
        except KeyError:
            click.secho(
                "Could not find the specified DSN in the config file. Please check the \"[alias_dsn]\" section in your myclirc.",
                err=True,
                fg="red",
            )
            sys.exit(1)
        else:
            mycli.dsn_alias = dsn

    if dsn_uri:
        uri = urlparse(dsn_uri)
        if not database:
            database = uri.path[1:]  # ignore the leading fwd slash
        if not user and uri.username is not None:
            user = unquote(uri.username)
        if not password and uri.password is not None:
            password = unquote(uri.password)
        if not host:
            host = uri.hostname
        if not port:
            port = uri.port

        if uri.query:
            dsn_params = parse_qs(uri.query)
        else:
            dsn_params = {}

        if params := dsn_params.get('ssl'):
            ssl_enable = ssl_enable or (params[0].lower() == 'true')
        if params := dsn_params.get('ssl_ca'):
            ssl_ca = ssl_ca or params[0]
            ssl_enable = True
        if params := dsn_params.get('ssl_capath'):
            ssl_capath = ssl_capath or params[0]
            ssl_enable = True
        if params := dsn_params.get('ssl_cert'):
            ssl_cert = ssl_cert or params[0]
            ssl_enable = True
        if params := dsn_params.get('ssl_key'):
            ssl_key = ssl_key or params[0]
            ssl_enable = True
        if params := dsn_params.get('ssl_cipher'):
            ssl_cipher = ssl_cipher or params[0]
            ssl_enable = True
        if params := dsn_params.get('tls_version'):
            tls_version = tls_version or params[0]
            ssl_enable = True
        if params := dsn_params.get('ssl_verify_server_cert'):
            ssl_verify_server_cert = ssl_verify_server_cert or (params[0].lower() == 'true')
            ssl_enable = True

    ssl_mode = ssl_mode or mycli.ssl_mode  # cli option or config option

    # if there is a mismatch between the ssl_mode value and other sources of ssl config, show a warning
    # specifically using "is False" to not pickup the case where ssl_enable is None (not set by the user)
    if ssl_enable and ssl_mode == "off" or ssl_enable is False and ssl_mode in ("auto", "on"):
        click.secho(
            f"Warning: The current ssl_mode value of '{ssl_mode}' is overriding the value provided by "
            f"either the --ssl/--no-ssl CLI options or a DSN URI parameter (ssl={ssl_enable}).",
            err=True,
            fg="yellow",
        )

    # configure SSL if ssl_mode is auto/on or if
    # ssl_enable = True (from --ssl or a DSN URI) and ssl_mode is None
    if ssl_mode in ("auto", "on") or (ssl_enable and ssl_mode is None):
        ssl = {
            "mode": ssl_mode,
            "enable": ssl_enable,
            "ca": ssl_ca and os.path.expanduser(ssl_ca),
            "cert": ssl_cert and os.path.expanduser(ssl_cert),
            "key": ssl_key and os.path.expanduser(ssl_key),
            "capath": ssl_capath,
            "cipher": ssl_cipher,
            "tls_version": tls_version,
            "check_hostname": ssl_verify_server_cert,
        }
        # remove empty ssl options
        ssl = {k: v for k, v in ssl.items() if v is not None}
    else:
        ssl = None

    if ssh_config_host:
        ssh_config = read_ssh_config(ssh_config_path).lookup(ssh_config_host)
        ssh_host = ssh_host if ssh_host else ssh_config.get("hostname")
        ssh_user = ssh_user if ssh_user else ssh_config.get("user")
        if ssh_config.get("port") and ssh_port == 22:
            # port has a default value, overwrite it if it's in the config
            ssh_port = int(ssh_config.get("port"))
        ssh_key_filename = ssh_key_filename if ssh_key_filename else ssh_config.get("identityfile", [None])[0]

    ssh_key_filename = ssh_key_filename and os.path.expanduser(ssh_key_filename)
    # Merge init-commands: global, DSN-specific, then CLI
    init_cmds: list[str] = []
    # 1) Global init-commands
    global_section = mycli.config.get("init-commands", {})
    for _, val in global_section.items():
        if isinstance(val, (list, tuple)):
            init_cmds.extend(val)
        elif val:
            init_cmds.append(val)
    # 2) DSN-specific init-commands
    if dsn:
        alias_section = mycli.config.get("alias_dsn.init-commands", {})
        if dsn in alias_section:
            val = alias_section.get(dsn)
            if isinstance(val, (list, tuple)):
                init_cmds.extend(val)
            elif val:
                init_cmds.append(val)
    # 3) CLI-provided init_command
    if init_command:
        init_cmds.append(init_command)

    combined_init_cmd = "; ".join(cmd.strip() for cmd in init_cmds if cmd)

    # --show-warnings / --no-show-warnings
    if show_warnings:
        mycli.show_warnings = show_warnings

    mycli.connect(
        database=database,
        user=user,
        passwd=password,
        host=host,
        port=port,
        socket=socket,
        local_infile=local_infile,
        ssl=ssl,
        ssh_user=ssh_user,
        ssh_host=ssh_host,
        ssh_port=ssh_port,
        ssh_password=ssh_password,
        ssh_key_filename=ssh_key_filename,
        init_command=combined_init_cmd,
        charset=charset,
        password_file=password_file,
    )

    if combined_init_cmd:
        click.echo(f"Executing init-command: {combined_init_cmd}", err=True)

    mycli.logger.debug("Launch Params: \n\tdatabase: %r\tuser: %r\thost: %r\tport: %r", database, user, host, port)

    #  --execute argument
    if execute:
        try:
            if csv:
                mycli.main_formatter.format_name = "csv"
                if execute.endswith(r"\G"):
                    execute = execute[:-2]
            elif table:
                if execute.endswith(r"\G"):
                    execute = execute[:-2]
            else:
                mycli.main_formatter.format_name = "tsv"

            mycli.run_query(execute)
            sys.exit(0)
        except Exception as e:
            click.secho(str(e), err=True, fg="red")
            sys.exit(1)

    if sys.stdin.isatty():
        mycli.run_cli()
    else:
        stdin = click.get_text_stream("stdin")
        try:
            stdin_text = stdin.read()
        except MemoryError:
            click.secho("Failed! Ran out of memory.", err=True, fg="red")
            click.secho("You might want to try the official mysql client.", err=True, fg="red")
            click.secho("Sorry... :(", err=True, fg="red")
            sys.exit(1)

        if mycli.destructive_warning and is_destructive(stdin_text):
            try:
                sys.stdin = open("/dev/tty")
                warn_confirmed = confirm_destructive_query(stdin_text)
            except (IOError, OSError):
                mycli.logger.warning("Unable to open TTY as stdin.")
            if not warn_confirmed:
                sys.exit(0)

        try:
            new_line = True

            if csv:
                mycli.main_formatter.format_name = "csv"
            elif not table:
                mycli.main_formatter.format_name = "tsv"

            mycli.run_query(stdin_text, new_line=new_line)
            sys.exit(0)
        except Exception as e:
            click.secho(str(e), err=True, fg="red")
            sys.exit(1)
    mycli.close()


def need_completion_refresh(queries: str) -> bool:
    """Determines if the completion needs a refresh by checking if the sql
    statement is an alter, create, drop or change db."""
    for query in sqlparse.split(queries):
        try:
            first_token = query.split()[0]
            if first_token.lower() in ("alter", "create", "use", "\\r", "\\u", "connect", "drop", "rename"):
                return True
        except Exception:
            return False
    return False


def need_completion_reset(queries: str) -> bool:
    """Determines if the statement is a database switch such as 'use' or '\\u'.
    When a database is changed the existing completions must be reset before we
    start the completion refresh for the new database.
    """
    for query in sqlparse.split(queries):
        try:
            first_token = query.split()[0]
            if first_token.lower() in ("use", "\\u"):
                return True
        except Exception:
            return False
    return False


def is_mutating(status: str | None) -> bool:
    """Determines if the statement is mutating based on the status."""
    if not status:
        return False

    mutating = {"insert", "update", "delete", "alter", "create", "drop", "replace", "truncate", "load", "rename"}
    return status.split(None, 1)[0].lower() in mutating


def is_select(status: str | None) -> bool:
    """Returns true if the first word in status is 'select'."""
    if not status:
        return False
    return status.split(None, 1)[0].lower() == "select"


def thanks_picker() -> str:
    import mycli

    lines = (resources.read_text(mycli, "AUTHORS") + resources.read_text(mycli, "SPONSORS")).split("\n")

    contents = []
    for line in lines:
        if m := re.match(r"^ *\* (.*)", line):
            contents.append(m.group(1))
    return choice(contents) if contents else 'our sponsors'


@prompt_register("edit-and-execute-command")
def edit_and_execute(event: KeyPressEvent) -> None:
    """Different from the prompt-toolkit default, we want to have a choice not
    to execute a query after editing, hence validate_and_handle=False."""
    buff = event.current_buffer
    buff.open_in_editor(validate_and_handle=False)


def read_ssh_config(ssh_config_path: str):
    ssh_config = paramiko.config.SSHConfig()
    try:
        with open(ssh_config_path) as f:
            ssh_config.parse(f)
    except FileNotFoundError as e:
        click.secho(str(e), err=True, fg="red")
        sys.exit(1)
    # Paramiko prior to version 2.7 raises Exception on parse errors.
    # In 2.7 it has become paramiko.ssh_exception.SSHException,
    # but let's catch everything for compatibility
    except Exception as err:
        click.secho(f"Could not parse SSH configuration file {ssh_config_path}:\n{err} ", err=True, fg="red")
        sys.exit(1)
    else:
        return ssh_config


if __name__ == "__main__":
    cli()
