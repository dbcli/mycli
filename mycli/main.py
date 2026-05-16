from __future__ import annotations

from io import TextIOWrapper
import logging
import os
import re
import sys
import threading
import traceback
from typing import IO, Any, Generator, Iterable, Literal

try:
    from pwd import getpwuid
except ImportError:
    pass
from textwrap import dedent
from urllib.parse import parse_qs, unquote, urlparse

from cli_helpers.tabular_output import TabularOutputFormatter
from cli_helpers.tabular_output.output_formatter import MISSING_VALUE as _DEFAULT_MISSING_VALUE
import click
import clickdc
import keyring
from prompt_toolkit.formatted_text import (
    to_formatted_text,
)
from prompt_toolkit.shortcuts import PromptSession
import pymysql
from pymysql.constants.CR import CR_SERVER_LOST
from pymysql.constants.ER import ACCESS_DENIED_ERROR, HANDSHAKE_ERROR
from pymysql.cursors import Cursor
import sqlparse

import mycli as mycli_package
from mycli.app_state import (
    AppStateMixin,
    configure_prompt_state,
    destructive_keywords_from_config,
    ensure_my_cnf_sections,
    llm_prompt_truncation,
    normalize_ssl_mode,
)
from mycli.cli_args import (
    DEFAULT_PROMPT,
    EMPTY_PASSWORD_FLAG_SENTINEL,
    CliArgs,
    preprocess_cli_args,
)
from mycli.clistyle import style_factory_helpers, style_factory_ptoolkit
from mycli.compat import WIN
from mycli.completion_refresher import CompletionRefresher
from mycli.config import get_mylogin_cnf_path, open_mylogin_cnf, read_config_files, str_to_bool, write_default_config
from mycli.constants import (
    DEFAULT_CHARSET,
    DEFAULT_HOST,
    DEFAULT_PORT,
    ER_MUST_CHANGE_PASSWORD_LOGIN,
    ISSUES_URL,
    REPO_URL,
)
from mycli.main_modes import repl as repl_package
from mycli.main_modes.batch import (
    main_batch_from_stdin,
    main_batch_with_progress_bar,
    main_batch_without_progress_bar,
)
from mycli.main_modes.checkup import main_checkup
from mycli.main_modes.execute import main_execute_from_cli
from mycli.main_modes.list_dsn import main_list_dsn
from mycli.main_modes.list_ssh_config import main_list_ssh_config
from mycli.main_modes.repl import main_repl, set_all_external_titles
from mycli.output import OutputMixin
from mycli.packages import special
from mycli.packages.cli_utils import filtered_sys_argv, is_valid_connection_scheme
from mycli.packages.filepaths import dir_path_exists, guess_socket_location
from mycli.packages.interactive_utils import confirm_destructive_query
from mycli.packages.special.favoritequeries import FavoriteQueries
from mycli.packages.special.main import ArgType, SpecialCommandAlias
from mycli.packages.sqlresult import SQLResult
from mycli.packages.ssh_utils import read_ssh_config
from mycli.packages.tabular_output import sql_format
from mycli.schema_prefetcher import SchemaPrefetcher
from mycli.sqlcompleter import SQLCompleter
from mycli.sqlexecute import SQLExecute
from mycli.types import Query

sqlparse.engine.grouping.MAX_GROUPING_DEPTH = None  # type: ignore[assignment]
sqlparse.engine.grouping.MAX_GROUPING_TOKENS = None  # type: ignore[assignment]

DEFAULT_MISSING_VALUE = _DEFAULT_MISSING_VALUE


class MyCli(AppStateMixin, OutputMixin):
    default_prompt = DEFAULT_PROMPT
    default_prompt_splitln = "\\u@\\h\\n(\\t):\\d>"
    max_len_prompt = 45
    defaults_suffix = None
    prompt_lines: int

    # In order of being loaded. Files lower in list override earlier ones.
    cnf_files: list[str | IO[str]] = [
        "/etc/my.cnf",
        "/etc/mysql/my.cnf",
        "/usr/local/etc/my.cnf",
        os.path.expanduser("~/.my.cnf"),
    ]

    # check XDG_CONFIG_HOME exists and not an empty string
    xdg_config_home = os.environ.get("XDG_CONFIG_HOME", "~/.config")
    system_config_files: list[str | IO[str]] = [
        "/etc/myclirc",
        os.path.join(os.path.expanduser(xdg_config_home), "mycli", "myclirc"),
    ]

    pwd_config_file = os.path.join(os.getcwd(), ".myclirc")

    def __init__(
        self,
        sqlexecute: SQLExecute | None = None,
        prompt: str | None = None,
        toolbar_format: str | None = None,
        logfile: TextIOWrapper | Literal[False] | None = None,
        defaults_suffix: str | None = None,
        defaults_file: str | None = None,
        login_path: str | None = None,
        auto_vertical_output: bool = False,
        warn: bool | None = None,
        myclirc: str = "~/.myclirc",
        show_warnings: bool | None = None,
        cli_verbosity: int = 0,
    ) -> None:
        self.sqlexecute = sqlexecute
        self.logfile = logfile
        self.defaults_suffix = defaults_suffix
        self.login_path = login_path
        self.toolbar_error_message: str | None = None
        self.prompt_session: PromptSession | None = None
        self._keepalive_counter = 0
        self.keepalive_ticks: int | None = 0
        self.sandbox_mode: bool = False

        # self.cnf_files is a class variable that stores the list of mysql
        # config files to read in at launch.
        # If defaults_file is specified then override the class variable with
        # defaults_file.
        if defaults_file:
            self.cnf_files = [defaults_file]

        # Load config.
        config_files: list[str | IO[str]] = self.system_config_files + [myclirc] + [self.pwd_config_file]
        c = self.config = read_config_files(config_files)
        # this parallel config exists to
        #  * compare with my.cnf
        #  * support the --checkup feature
        # todo: after removing my.cnf, create the parallel configs only when --checkup is set
        self.config_without_package_defaults = read_config_files(config_files, ignore_package_defaults=True)
        # this parallel config exists to compare with my.cnf support the --checkup feature
        self.config_without_user_options = read_config_files(config_files, ignore_user_options=True)
        self.multi_line = c["main"].as_bool("multi_line")
        self.key_bindings = c["main"]["key_bindings"]
        self.emacs_ttimeoutlen = c['keys'].as_float('emacs_ttimeoutlen')
        self.vi_ttimeoutlen = c['keys'].as_float('vi_ttimeoutlen')
        special.set_timing_enabled(c["main"].as_bool("timing"))
        special.set_show_favorite_query(c["main"].as_bool("show_favorite_query"))
        if show_warnings is not None:
            special.set_show_warnings_enabled(show_warnings)
        else:
            special.set_show_warnings_enabled(c['main'].as_bool('show_warnings'))
        self.beep_after_seconds = float(c["main"]["beep_after_seconds"] or 0)
        self.default_keepalive_ticks = c['connection'].as_int('default_keepalive_ticks')

        FavoriteQueries.instance = FavoriteQueries.from_config(self.config)

        self.dsn_alias: str | None = None
        self.main_formatter = TabularOutputFormatter(format_name=c["main"]["table_format"])
        self.redirect_formatter = TabularOutputFormatter(format_name=c["main"].get("redirect_format", "csv"))
        sql_format.register_new_formatter(self.main_formatter)
        sql_format.register_new_formatter(self.redirect_formatter)
        self.main_formatter.mycli = self
        self.redirect_formatter.mycli = self
        self.syntax_style = c["main"]["syntax_style"]
        self.verbosity = -1 if c["main"].as_bool("less_chatty") else 0
        if cli_verbosity:
            self.verbosity = cli_verbosity
        self.cli_style = c["colors"]
        self.ptoolkit_style = style_factory_ptoolkit(self.syntax_style, self.cli_style)
        self.helpers_style = style_factory_helpers(self.syntax_style, self.cli_style)
        self.helpers_warnings_style = style_factory_helpers(self.syntax_style, self.cli_style, warnings=True)
        self.wider_completion_menu = c["main"].as_bool("wider_completion_menu")
        c_dest_warning = c["main"].as_bool("destructive_warning")
        self.destructive_warning = c_dest_warning if warn is None else warn
        self.login_path_as_host = c["main"].as_bool("login_path_as_host")
        self.post_redirect_command = c['main'].get('post_redirect_command')
        self.null_string = c['main'].get('null_string')
        self.numeric_alignment = c['main'].get('numeric_alignment', 'right')
        self.binary_display = c['main'].get('binary_display')
        self.llm_prompt_field_truncate, self.llm_prompt_section_truncate = llm_prompt_truncation(c)

        self.ssl_mode, ssl_mode_error = normalize_ssl_mode(c)
        if ssl_mode_error:
            self.echo(ssl_mode_error, err=True, fg="red")

        # read from cli argument or user config file
        self.auto_vertical_output = auto_vertical_output or c["main"].as_bool("auto_vertical_output")

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
        self.prefetch_schemas_mode = c["main"].get("prefetch_schemas_mode", "always") or "always"
        raw_prefetch_list = c["main"].as_list("prefetch_schemas_list") if "prefetch_schemas_list" in c["main"] else []
        self.prefetch_schemas_list = [s.strip() for s in raw_prefetch_list if s and s.strip()]
        self.schema_prefetcher = SchemaPrefetcher(self)

        self.logger = logging.getLogger(__name__)
        self.initialize_logging()

        keyword_casing = c["main"].get("keyword_casing", "auto")

        self.highlight_preview = c['search'].as_bool('highlight_preview')

        self.query_history: list[Query] = []

        # Initialize completer.
        self.smart_completion = c["main"].as_bool("smart_completion")
        self.completer = SQLCompleter(
            self.smart_completion, supported_formats=self.main_formatter.supported_formats, keyword_casing=keyword_casing
        )
        self._completer_lock = threading.Lock()

        self.min_completion_trigger = c["main"].as_int("min_completion_trigger")
        # a hack, pending a better way to handle settings and state
        repl_package.MIN_COMPLETION_TRIGGER = self.min_completion_trigger
        self.last_prompt_message = to_formatted_text('')
        self.last_custom_toolbar_message = to_formatted_text('')

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
        ensure_my_cnf_sections(self.my_cnf)
        prompt_cnf = self.read_my_cnf(self.my_cnf, ["prompt"])["prompt"]
        configure_prompt_state(self, c, prompt, prompt_cnf, toolbar_format)
        self.prompt_session = None
        self.destructive_keywords = destructive_keywords_from_config(c)
        special.set_destructive_keywords(self.destructive_keywords)

    def close(self) -> None:
        if hasattr(self, 'schema_prefetcher'):
            self.schema_prefetcher.stop()
        if self.sqlexecute is not None:
            self.sqlexecute.close()

    def register_special_commands(self) -> None:
        special.register_special_command(
            self.change_db,
            "use",
            "use <database>",
            "Change to a new database.",
            aliases=[SpecialCommandAlias("\\u", case_sensitive=False)],
        )
        special.register_special_command(
            self.manual_reconnect,
            "connect",
            "connect [database]",
            "Reconnect to the server, optionally switching databases.",
            case_sensitive=True,
            aliases=[SpecialCommandAlias("\\r", case_sensitive=True)],
        )
        special.register_special_command(
            self.refresh_completions,
            "rehash",
            "rehash",
            "Refresh auto-completions.",
            arg_type=ArgType.NO_QUERY,
            aliases=[SpecialCommandAlias("\\#", case_sensitive=False)],
        )
        special.register_special_command(
            self.change_table_format,
            "tableformat",
            "tableformat <format>",
            "Change the table format used to output interactive results.",
            case_sensitive=True,
            aliases=[SpecialCommandAlias("\\T", case_sensitive=True)],
        )
        special.register_special_command(
            self.change_redirect_format,
            "redirectformat",
            "redirectformat <format>",
            "Change the table format used to output redirected results.",
            case_sensitive=True,
            aliases=[SpecialCommandAlias("\\Tr", case_sensitive=True)],
        )
        special.register_special_command(
            self.execute_from_file,
            "source",
            "source <filename>",
            "Execute queries from a file.",
            aliases=[SpecialCommandAlias("\\.", case_sensitive=False)],
        )
        special.register_special_command(
            self.change_prompt_format,
            "prompt",
            "prompt <string>",
            "Change prompt format.",
            case_sensitive=True,
            aliases=[SpecialCommandAlias("\\R", case_sensitive=True)],
        )

    def manual_reconnect(self, arg: str = "", **_) -> Generator[SQLResult, None, None]:
        """
        Interactive method to use for the \r command, so that the utility method
        may be cleanly used elsewhere.
        """
        if not self.reconnect(database=arg):
            yield SQLResult(status="Not connected")
        elif not arg or arg == '``':
            yield SQLResult()
        else:
            yield self.change_db(arg).send(None)

    def change_table_format(self, arg: str, **_) -> Generator[SQLResult, None, None]:
        try:
            self.main_formatter.format_name = arg
            yield SQLResult(status=f"Changed table format to {arg}")
        except ValueError:
            msg = f"Table format {arg} not recognized. Allowed formats:"
            for table_type in self.main_formatter.supported_formats:
                msg += f"\n\t{table_type}"
            yield SQLResult(status=msg)

    def change_redirect_format(self, arg: str, **_) -> Generator[SQLResult, None, None]:
        try:
            self.redirect_formatter.format_name = arg
            yield SQLResult(status=f"Changed redirect format to {arg}")
        except ValueError:
            msg = f"Redirect format {arg} not recognized. Allowed formats:"
            for table_type in self.redirect_formatter.supported_formats:
                msg += f"\n\t{table_type}"
            yield SQLResult(status=msg)

    def change_db(self, arg: str, **_) -> Generator[SQLResult, None, None]:
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

        # todo: this jump back to repl.py is a sign that separation is incomplete.
        # also: it should not be needed.  Don't titles update on every new prompt?
        set_all_external_titles(self)

        yield SQLResult(status=msg)

    def execute_from_file(self, arg: str, **_) -> Iterable[SQLResult]:
        if not arg:
            message = "Missing required argument: filename."
            return [SQLResult(status=message)]
        try:
            with open(os.path.expanduser(arg)) as f:
                query = f.read()
        except IOError as e:
            return [SQLResult(status=str(e))]

        if self.destructive_warning and confirm_destructive_query(self.destructive_keywords, query) is False:
            message = "Wise choice. Command execution stopped."
            return [SQLResult(status=message)]

        assert isinstance(self.sqlexecute, SQLExecute)
        return self.sqlexecute.run(query)

    def change_prompt_format(self, arg: str, **_) -> list[SQLResult]:
        """
        Change the prompt format.
        """
        if not arg:
            message = "Missing required argument, format."
            return [SQLResult(status=message)]

        self.prompt_format = arg
        return [SQLResult(status=f"Changed prompt format to {arg}")]

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

    def connect(
        self,
        database: str | None = "",
        user: str | None = "",
        passwd: str | int | None = None,
        host: str | None = "",
        port: str | int | None = "",
        socket: str | None = "",
        character_set: str | None = "",
        local_infile: bool | None = False,
        ssl: dict[str, Any] | None = None,
        ssh_user: str | None = "",
        ssh_host: str | None = "",
        ssh_port: int = 22,
        ssh_password: str | None = "",
        ssh_key_filename: str | None = "",
        init_command: str | None = "",
        unbuffered: bool | None = None,
        use_keyring: bool | None = None,
        reset_keyring: bool | None = None,
        keepalive_ticks: int | None = None,
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
        user_connection_config = self.config_without_package_defaults.get('connection', {})
        self.keepalive_ticks = keepalive_ticks

        int_port = port and int(port)
        if not int_port:
            int_port = DEFAULT_PORT
            if not host or host == DEFAULT_HOST:
                socket = (
                    socket
                    or user_connection_config.get("default_socket")
                    or cnf["socket"]
                    or cnf["default_socket"]
                    or guess_socket_location()
                )

        passwd = passwd if isinstance(passwd, (str, int)) else cnf["password"]

        # default_character_set doesn't check in self.config_without_package_defaults, because the
        # option already existed before the my.cnf deprecation.  For the same reason,
        # default_character_set can be in [connection] or [main].
        if not character_set:
            if 'default_character_set' in self.config['connection']:
                character_set = self.config['connection']['default_character_set']
            elif 'default_character_set' in self.config['main']:
                character_set = self.config['main']['default_character_set']
            elif 'default_character_set' in cnf:
                character_set = cnf['default_character_set']
            elif 'default-character-set' in cnf:
                character_set = cnf['default-character-set']
        if not character_set:
            character_set = DEFAULT_CHARSET

        # Favor whichever local_infile option is set.
        use_local_infile = False
        for local_infile_option in (
            local_infile,
            user_connection_config.get('default_local_infile'),
            cnf['local_infile'],
            cnf['local-infile'],
            cnf['loose_local_infile'],
            cnf['loose-local-infile'],
            False,
        ):
            try:
                use_local_infile = str_to_bool(local_infile_option or '')
                break
            except (TypeError, ValueError):
                pass

        # temporary my.cnf override mappings
        if 'default_ssl_ca' in user_connection_config:
            cnf['ssl-ca'] = user_connection_config.get('default_ssl_ca') or None
        if 'default_ssl_cert' in user_connection_config:
            cnf['ssl-cert'] = user_connection_config.get('default_ssl_cert') or None
        if 'default_ssl_key' in user_connection_config:
            cnf['ssl-key'] = user_connection_config.get('default_ssl_key') or None
        if 'default_ssl_cipher' in user_connection_config:
            cnf['ssl-cipher'] = user_connection_config.get('default_ssl_cipher') or None
        if 'default_ssl_verify_server_cert' in user_connection_config:
            cnf['ssl-verify-server-cert'] = user_connection_config.get('default_ssl_verify_server_cert') or None

        # todo: rewrite the merge method using self.config['connection'] instead of cnf, after removing my.cnf support
        ssl_config_or_none: dict[str, Any] | None = self.merge_ssl_with_cnf(ssl_config, cnf)

        # default_ssl_ca_path is not represented in my.cnf
        if 'default_ssl_ca_path' in self.config['connection'] and (not ssl_config_or_none or not ssl_config_or_none.get('capath')):
            if ssl_config_or_none is None:
                ssl_config_or_none = {}
            ssl_config_or_none['capath'] = self.config['connection']['default_ssl_ca_path'] or False

        # prune lone check_hostname=False
        if not any(v for v in ssl_config.values()):
            ssl_config_or_none = None

        # password hierarchy
        # 1. -p / --pass/--password CLI options
        # 2. --password-file CLI option
        # 3. envvar (MYSQL_PWD)
        # 4. DSN (mysql://user:password)
        # 5. cnf (.my.cnf / etc)
        # 6. keyring

        keyring_identifier = f'{user}@{host}:{"" if socket else int_port}:{socket or ""}'
        keyring_domain = 'mycli.net'
        keyring_retrieved_cleanly = False

        if passwd is None and use_keyring and not reset_keyring:
            passwd = keyring.get_password(keyring_domain, keyring_identifier)
            if passwd is not None:
                keyring_retrieved_cleanly = True

        # prompt for password if requested by user
        if passwd == EMPTY_PASSWORD_FLAG_SENTINEL:
            passwd = click.prompt(f"Enter password for {user}", hide_input=True, show_default=False, default='', type=str, err=True)
            keyring_retrieved_cleanly = False

        # should not fail, but will help the typechecker
        assert not isinstance(passwd, int)

        connection_info: dict[Any, Any] = {
            "database": database,
            "user": user,
            "password": passwd,
            "host": host,
            "port": int_port,
            "socket": socket,
            "character_set": character_set,
            "local_infile": use_local_infile,
            "ssl": ssl_config_or_none,
            "ssh_user": ssh_user,
            "ssh_host": ssh_host,
            "ssh_port": int(ssh_port) if ssh_port else None,
            "ssh_password": ssh_password,
            "ssh_key_filename": ssh_key_filename,
            "init_command": init_command,
            "unbuffered": unbuffered,
        }

        def _update_keyring(password: str | None, keyring_retrieved_cleanly: bool):
            if not password:
                return
            if reset_keyring or (use_keyring and not keyring_retrieved_cleanly):
                try:
                    saved_pw = keyring.get_password(keyring_domain, keyring_identifier)
                    if password != saved_pw or reset_keyring:
                        keyring.set_password(keyring_domain, keyring_identifier, password)
                        click.secho(f'Password saved to the system keyring at {keyring_domain}/{keyring_identifier}', err=True)
                except Exception as e:
                    click.secho(f'Password not saved to the system keyring: {e}', err=True, fg='red')

        def _connect(
            retry_ssl: bool = False,
            retry_password: bool = False,
            keyring_save_eligible: bool = True,
            keyring_retrieved_cleanly: bool = False,
        ) -> None:
            try:
                if keyring_save_eligible:
                    _update_keyring(connection_info["password"], keyring_retrieved_cleanly=keyring_retrieved_cleanly)
                self.sqlexecute = SQLExecute(**connection_info)
            except pymysql.OperationalError as e1:
                if e1.args[0] == HANDSHAKE_ERROR and ssl is not None and ssl.get("mode", None) == "auto":
                    # if we already tried and failed to connect without SSL, raise the error
                    if retry_ssl:
                        raise e1
                    # disable SSL and try to connect again
                    connection_info["ssl"] = None
                    _connect(
                        retry_ssl=True, keyring_retrieved_cleanly=keyring_retrieved_cleanly, keyring_save_eligible=keyring_save_eligible
                    )
                elif e1.args[0] == ACCESS_DENIED_ERROR and connection_info["password"] is None:
                    # if we already tried and failed to connect with a new password, raise the error
                    if retry_password:
                        raise e1
                    # ask the user for a new password and try to connect again
                    new_password = click.prompt(
                        f"Enter password for {user}", hide_input=True, show_default=False, default='', type=str, err=True
                    )
                    connection_info["password"] = new_password
                    keyring_retrieved_cleanly = False
                    _connect(
                        retry_password=True,
                        keyring_retrieved_cleanly=keyring_retrieved_cleanly,
                        keyring_save_eligible=keyring_save_eligible,
                    )
                elif e1.args[0] == ER_MUST_CHANGE_PASSWORD_LOGIN:
                    self.echo(
                        "Your password has expired and the server rejected the connection.",
                        err=True,
                        fg='red',
                    )
                    raise e1
                elif e1.args[0] == CR_SERVER_LOST:
                    self.echo(
                        (
                            "Connection to server lost. If this error persists, it may be a mismatch between the server and "
                            "client SSL configuration. To troubleshoot the issue, try --ssl-mode=off or --ssl-mode=on."
                        ),
                        err=True,
                        fg='red',
                    )
                    raise e1
                else:
                    raise e1

        try:
            if not WIN and socket:
                try:
                    socket_owner = getpwuid(os.stat(socket).st_uid).pw_name
                except KeyError:
                    socket_owner = '<unknown>'
                self.echo(f"Connecting to socket {socket}, owned by user {socket_owner}", err=True)
                try:
                    _connect(keyring_retrieved_cleanly=keyring_retrieved_cleanly)
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
                        host = DEFAULT_HOST
                        port = DEFAULT_PORT
                        # todo should reload the keyring identifier here instead of invalidating
                        _connect(keyring_save_eligible=False)
                    else:
                        raise e
            else:
                host = host or DEFAULT_HOST
                port = port or DEFAULT_PORT
                # could try loading the keyring again here instead of assuming nothing important changed

                # Bad ports give particularly daft error messages
                try:
                    port = int(port)
                except ValueError:
                    self.echo(f"Error: Invalid port number: '{port}'.", err=True, fg="red")
                    sys.exit(1)

                _connect(keyring_retrieved_cleanly=keyring_retrieved_cleanly)

            # Check if SQLExecute detected sandbox mode during connection
            if self.sqlexecute and self.sqlexecute.sandbox_mode:
                self.sandbox_mode = True
                self.echo(
                    "Your password has expired. Use ALTER USER or SET PASSWSORD to set a new password, or quit.",
                    err=True,
                    fg='yellow',
                )
        except Exception as e:  # Connecting to a database could fail.
            self.logger.debug("Database connection failed: %r.", e)
            self.logger.error("traceback: %r", traceback.format_exc())
            self.echo(str(e), err=True, fg="red")
            sys.exit(1)

    def run_cli(self) -> None:
        main_repl(self)

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
            # if a database is currently selected, set it on the conn again
            if self.sqlexecute.dbname:
                self.sqlexecute.conn.select_db(self.sqlexecute.dbname)
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

    def refresh_completions(self, reset: bool = False) -> list[SQLResult]:
        # Cancel any in-flight schema prefetch before the completer is
        # replaced.  Loaded-schema bookkeeping is intentionally preserved
        # so switching between already-loaded schemas does not re-fetch.
        self.schema_prefetcher.stop()

        assert self.sqlexecute is not None
        if reset:
            # Update the active completer's current-schema pointer right
            # away so unqualified completions reflect a schema switch
            # even before the background refresh finishes.
            with self._completer_lock:
                self.completer.set_dbname(self.sqlexecute.dbname)
        self.completion_refresher.refresh(
            self.sqlexecute,
            self._on_completions_refreshed,
            {
                "smart_completion": self.smart_completion,
                "supported_formats": self.main_formatter.supported_formats,
                "keyword_casing": self.completer.keyword_casing,
            },
        )

        return [SQLResult(status="Auto-completion refresh started in the background.")]

    def _on_completions_refreshed(self, new_completer: SQLCompleter) -> None:
        """Swap the completer object in cli with the newly created completer."""
        with self._completer_lock:
            new_completer.copy_other_schemas_from(self.completer, exclude=new_completer.dbname)
            self.completer = new_completer

        if self.prompt_session:
            # After refreshing, redraw the CLI to clear the statusbar
            # "Refreshing completions..." indicator
            self.prompt_session.app.invalidate()

        # Kick off background prefetch for any extra schemas configured
        # via ``prefetch_schemas_mode`` so users get cross-schema completions.
        self.schema_prefetcher.start_configured()

    def run_query(
        self,
        query: str,
        checkpoint: TextIOWrapper | None = None,
        new_line: bool = True,
    ) -> None:
        """Runs *query*."""
        assert self.sqlexecute is not None
        self.log_query(query)
        results = self.sqlexecute.run(query)
        for result in results:
            self.main_formatter.query = query
            self.redirect_formatter.query = query
            output = self.format_sqlresult(
                result,
                is_expanded=special.is_expanded_output(),
                is_redirected=special.is_redirected(),
                null_string=self.null_string,
                numeric_alignment=self.numeric_alignment,
                binary_display=self.binary_display,
            )
            for line in output:
                self.log_output(line)
                click.echo(line, nl=new_line)

            # get and display warnings if enabled
            if special.is_show_warnings_enabled() and isinstance(result.rows, Cursor) and result.rows.warning_count > 0:
                warnings = self.sqlexecute.run("SHOW WARNINGS")
                for warning in warnings:
                    output = self.format_sqlresult(
                        warning,
                        is_expanded=special.is_expanded_output(),
                        is_redirected=special.is_redirected(),
                        null_string=self.null_string,
                        numeric_alignment=self.numeric_alignment,
                        binary_display=self.binary_display,
                        is_warnings_style=True,
                    )
                    for line in output:
                        click.echo(line, nl=new_line)
        if checkpoint:
            checkpoint.write(query.rstrip('\n') + '\n')
            checkpoint.flush()

    def get_last_query(self) -> str | None:
        """Get the last query executed or None."""
        return self.query_history[-1][0] if self.query_history else None


@click.command()
@clickdc.adddc('cli_args', CliArgs)
@click.version_option(mycli_package.__version__, '--version', '-V', help="Output mycli's version.")
def click_entrypoint(
    cli_args: CliArgs,
) -> None:
    """A MySQL terminal client with auto-completion and syntax highlighting.

    \b
    Examples:
      - mycli my_database
      - mycli -u my_user -h my_host.com my_database
      - mycli mysql://my_user@my_host.com:3306/my_database

    """

    cli_verbosity = preprocess_cli_args(cli_args, is_valid_connection_scheme)

    mycli = MyCli(
        prompt=cli_args.prompt,
        toolbar_format=cli_args.toolbar,
        logfile=cli_args.logfile,
        defaults_suffix=cli_args.defaults_group_suffix,
        defaults_file=cli_args.defaults_file,
        login_path=cli_args.login_path,
        auto_vertical_output=cli_args.auto_vertical_output,
        warn=cli_args.warn,
        myclirc=cli_args.myclirc,
        show_warnings=cli_args.show_warnings,
        cli_verbosity=cli_verbosity,
    )

    if cli_args.checkup:
        main_checkup(mycli)
        sys.exit(0)

    if cli_args.csv and cli_args.format not in [None, 'csv']:
        click.secho("Conflicting --csv and --format arguments.", err=True, fg="red")
        sys.exit(1)

    if cli_args.table and cli_args.format not in [None, 'table']:
        click.secho("Conflicting --table and --format arguments.", err=True, fg="red")
        sys.exit(1)

    if not cli_args.format:
        cli_args.format = 'default'

    if cli_args.csv:
        cli_args.format = 'csv'

    if cli_args.table:
        cli_args.format = 'table'

    if cli_args.deprecated_ssl is not None:
        click.secho(
            "Warning: The --ssl/--no-ssl CLI options are deprecated and will be removed in a future release. "
            "Please use the \"default_ssl_mode\" config option or --ssl-mode CLI flag instead. "
            f"See issue {ISSUES_URL}/1507",
            err=True,
            fg="yellow",
        )

    # ssh_port and ssh_config_path have truthy defaults and are not included
    if (
        any([
            cli_args.ssh_user,
            cli_args.ssh_host,
            cli_args.ssh_password,
            cli_args.ssh_key_filename,
            cli_args.list_ssh_config,
            cli_args.ssh_config_host,
        ])
        and not cli_args.ssh_warning_off
    ):
        click.secho(
            f"Warning: The built-in SSH functionality is deprecated and will be removed in a future release. See issue {ISSUES_URL}/1464",
            err=True,
            fg="red",
        )

    if cli_args.list_dsn:
        sys.exit(main_list_dsn(mycli))

    if cli_args.list_ssh_config:
        sys.exit(main_list_ssh_config(mycli, cli_args))

    if 'MYSQL_UNIX_PORT' in os.environ:
        # deprecated 2026-03
        click.secho(
            "The MYSQL_UNIX_PORT environment variable is deprecated in favor of MYSQL_UNIX_SOCKET.  "
            "MYSQL_UNIX_PORT will be removed in a future release.",
            err=True,
            fg="red",
        )
        if not cli_args.socket:
            cli_args.socket = os.environ['MYSQL_UNIX_PORT']

    if 'DSN' in os.environ:
        # deprecated 2026-03
        click.secho(
            "The DSN environment variable is deprecated in favor of MYSQL_DSN.  Support for DSN will be removed in a future release.",
            err=True,
            fg="red",
        )
        if not cli_args.dsn:
            cli_args.dsn = os.environ['DSN']

    # Choose which ever one has a valid value.
    database = cli_args.dbname or cli_args.database

    dsn_uri = None

    # Treat the database argument as a DSN alias only if it matches a configured alias
    # todo why is port tested but not socket?
    truthy_password = cli_args.password not in (None, EMPTY_PASSWORD_FLAG_SENTINEL)
    if (
        database
        and "://" not in database
        and not any([
            cli_args.user,
            truthy_password,
            cli_args.host,
            cli_args.port,
            cli_args.login_path,
        ])
        and database in mycli.config.get("alias_dsn", {})
    ):
        cli_args.dsn, database = database, ""

    if database and "://" in database:
        dsn_uri, database = database, ""

    if cli_args.dsn:
        try:
            dsn_uri = mycli.config["alias_dsn"][cli_args.dsn]
        except KeyError:
            is_valid_scheme, scheme = is_valid_connection_scheme(cli_args.dsn)
            if is_valid_scheme:
                dsn_uri = cli_args.dsn
            else:
                click.secho(
                    "Could not find the specified DSN in the config file. Please check the \"[alias_dsn]\" section in your myclirc.",
                    err=True,
                    fg="red",
                )
                sys.exit(1)
        else:
            mycli.dsn_alias = cli_args.dsn

    if dsn_uri:
        uri = urlparse(dsn_uri)
        if not database:
            database = uri.path[1:]  # ignore the leading fwd slash
        if not cli_args.user and uri.username is not None:
            cli_args.user = unquote(uri.username)
        # todo: rationalize the behavior of empty-string passwords here
        if not cli_args.password and uri.password is not None:
            cli_args.password = unquote(uri.password)
        if not cli_args.host:
            cli_args.host = uri.hostname
        if not cli_args.port:
            cli_args.port = uri.port

        if uri.query:
            dsn_params = parse_qs(uri.query)
        else:
            dsn_params = {}

        if params := dsn_params.get('ssl'):
            click.secho(
                'Warning: The "ssl" DSN URI parameter is deprecated and will be removed in a future release. '
                'Please use the "ssl_mode" parameter instead. '
                f'See issue {ISSUES_URL}/1507',
                err=True,
                fg='yellow',
            )
            if params[0].lower() == 'true':
                cli_args.ssl_mode = 'on'
        if params := dsn_params.get('ssl_mode'):
            cli_args.ssl_mode = cli_args.ssl_mode or params[0]
        if params := dsn_params.get('ssl_ca'):
            cli_args.ssl_ca = cli_args.ssl_ca or params[0]
            cli_args.ssl_mode = cli_args.ssl_mode or 'on'
        if params := dsn_params.get('ssl_capath'):
            cli_args.ssl_capath = cli_args.ssl_capath or params[0]
            cli_args.ssl_mode = cli_args.ssl_mode or 'on'
        if params := dsn_params.get('ssl_cert'):
            cli_args.ssl_cert = cli_args.ssl_cert or params[0]
            cli_args.ssl_mode = cli_args.ssl_mode or 'on'
        if params := dsn_params.get('ssl_key'):
            cli_args.ssl_key = cli_args.ssl_key or params[0]
            cli_args.ssl_mode = cli_args.ssl_mode or 'on'
        if params := dsn_params.get('ssl_cipher'):
            cli_args.ssl_cipher = cli_args.ssl_cipher or params[0]
            cli_args.ssl_mode = cli_args.ssl_mode or 'on'
        if params := dsn_params.get('tls_version'):
            cli_args.tls_version = cli_args.tls_version or params[0]
            cli_args.ssl_mode = cli_args.ssl_mode or 'on'
        if params := dsn_params.get('ssl_verify_server_cert'):
            cli_args.ssl_verify_server_cert = cli_args.ssl_verify_server_cert or (params[0].lower() == 'true')
            cli_args.ssl_mode = cli_args.ssl_mode or 'on'
        if params := dsn_params.get('socket'):
            cli_args.socket = cli_args.socket or params[0]
        if params := dsn_params.get('keepalive_ticks'):
            if cli_args.keepalive_ticks is None:
                cli_args.keepalive_ticks = int(params[0])
        if params := dsn_params.get('character_set'):
            cli_args.character_set = cli_args.character_set or params[0]

    keepalive_ticks = cli_args.keepalive_ticks if cli_args.keepalive_ticks is not None else mycli.default_keepalive_ticks
    ssl_mode = cli_args.ssl_mode or mycli.ssl_mode

    # if there is a mismatch between the ssl_mode value and other sources of ssl config, show a warning
    # specifically using "is False" to not pickup the case where cli_args.deprecated_ssl is None (not set by the user)
    if cli_args.deprecated_ssl and ssl_mode == "off" or cli_args.deprecated_ssl is False and ssl_mode in ("auto", "on"):
        click.secho(
            f"Warning: The current ssl_mode value of '{ssl_mode}' is overriding the value provided by "
            f"either the --ssl/--no-ssl CLI options or a DSN URI parameter (ssl={cli_args.deprecated_ssl}).",
            err=True,
            fg="yellow",
        )

    # configure SSL if ssl_mode is auto/on or if
    # cli_args.deprecated_ssl = True (from --ssl or a DSN URI) and ssl_mode is None
    if ssl_mode in ("auto", "on") or (cli_args.deprecated_ssl and ssl_mode is None):
        if cli_args.socket and ssl_mode == 'auto':
            ssl = None
        else:
            ssl = {
                "mode": ssl_mode,
                "enable": cli_args.deprecated_ssl,  # todo: why is this set at all?
                "ca": cli_args.ssl_ca and os.path.expanduser(cli_args.ssl_ca),
                "cert": cli_args.ssl_cert and os.path.expanduser(cli_args.ssl_cert),
                "key": cli_args.ssl_key and os.path.expanduser(cli_args.ssl_key),
                "capath": cli_args.ssl_capath,
                "cipher": cli_args.ssl_cipher,
                "tls_version": cli_args.tls_version,
                "check_hostname": cli_args.ssl_verify_server_cert,
            }
            # remove empty ssl options
            ssl = {k: v for k, v in ssl.items() if v is not None}
    else:
        ssl = None

    if cli_args.ssh_config_host:
        ssh_config = read_ssh_config(cli_args.ssh_config_path).lookup(cli_args.ssh_config_host)
        ssh_host = cli_args.ssh_host if cli_args.ssh_host else ssh_config.get("hostname")
        ssh_user = cli_args.ssh_user if cli_args.ssh_user else ssh_config.get("user")
        if ssh_config.get("port") and cli_args.ssh_port == 22:
            # port has a default value, overwrite it if it's in the config
            ssh_port = int(ssh_config.get("port"))
        else:
            ssh_port = cli_args.ssh_port
        ssh_key_filename = cli_args.ssh_key_filename if cli_args.ssh_key_filename else ssh_config.get("identityfile", [None])[0]
    else:
        ssh_host = cli_args.ssh_host
        ssh_user = cli_args.ssh_user
        ssh_port = cli_args.ssh_port
        ssh_key_filename = cli_args.ssh_key_filename

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
    if cli_args.dsn:
        alias_section = mycli.config.get("alias_dsn.init-commands", {})
        if cli_args.dsn in alias_section:
            val = alias_section.get(cli_args.dsn)
            if isinstance(val, (list, tuple)):
                init_cmds.extend(val)
            elif val:
                init_cmds.append(val)
    # 3) CLI-provided init_command
    if cli_args.init_command:
        init_cmds.append(cli_args.init_command)

    combined_init_cmd = "; ".join(cmd.strip() for cmd in init_cmds if cmd)

    if cli_args.use_keyring is not None and cli_args.use_keyring.lower() == 'reset':
        use_keyring = True
        reset_keyring = True
    elif cli_args.use_keyring is None:
        use_keyring = str_to_bool(mycli.config['main'].get('use_keyring', 'False'))
        reset_keyring = False
    else:
        use_keyring = str_to_bool(cli_args.use_keyring)
        reset_keyring = False

    # todo: removeme after a period of transition
    for tup in [
        ('client', 'prompt', 'prompt', 'main', 'prompt'),
        ('client', 'pager', 'pager', 'main', 'pager'),
        ('client', 'skip-pager', 'skip-pager', 'main', 'enable_pager'),
        # this is a white lie, because default_character_set can actually be read from the package config
        ('client', 'default-character-set', 'default-character-set', 'connection', 'default_character_set'),
        # local-infile can be read from both sections
        ('mysqld', 'local-infile', 'local-infile', 'connection', 'default_local_infile'),
        ('client', 'local-infile', 'local-infile', 'connection', 'default_local_infile'),
        ('mysqld', 'loose-local-infile', 'loose-local-infile', 'connection', 'default_local_infile'),
        ('client', 'loose-local-infile', 'loose-local-infile', 'connection', 'default_local_infile'),
        # todo: in the future we should add default_port, etc, but only in .myclirc
        # they are currently ignored in my.cnf
        ('mysqld', 'default_socket', 'socket', 'connection', 'default_socket'),
        ('client', 'ssl-ca', 'ssl-ca', 'connection', 'default_ssl_ca'),
        ('client', 'ssl-cert', 'ssl-cert', 'connection', 'default_ssl_cert'),
        ('client', 'ssl-key', 'ssl-key', 'connection', 'default_ssl_key'),
        ('client', 'ssl-cipher', 'ssl-cipher', 'connection', 'default_ssl_cipher'),
        ('client', 'ssl-verify-server-cert', 'ssl-verify-server-cert', 'connection', 'default_ssl_verify_server_cert'),
    ]:
        (
            mycnf_section_name,
            mycnf_item_name,
            printable_mycnf_item_name,
            myclirc_section_name,
            myclirc_item_name,
        ) = tup
        if str_to_bool(mycli.config['main'].get('my_cnf_transition_done', 'False')):
            break
        if (
            mycli.my_cnf[mycnf_section_name].get(mycnf_item_name) is None
            and mycli.my_cnf[mycnf_section_name].get(mycnf_item_name.replace('-', '_')) is None
        ):
            continue
        user_section = mycli.config_without_package_defaults.get(myclirc_section_name, {})
        if user_section.get(myclirc_item_name) is None:
            cnf_value = mycli.my_cnf[mycnf_section_name].get(mycnf_item_name)
            if cnf_value is None:
                cnf_value = mycli.my_cnf[mycnf_section_name].get(mycnf_item_name.replace('-', '_'))
            click.secho(
                dedent(
                    f"""
                    Reading configuration from my.cnf files is deprecated.
                    See {ISSUES_URL}/1490 .
                    The cause of this message is the following in a my.cnf file without a corresponding
                    ~/.myclirc entry:

                        [{mycnf_section_name}]
                        {printable_mycnf_item_name} = {cnf_value}

                    To suppress this message, remove the my.cnf item add or the following to ~/.myclirc:

                        [{myclirc_section_name}]
                        {myclirc_item_name} = <value>

                    The ~/.myclirc setting will take precedence.  In the future, the my.cnf will be ignored.

                    Values are documented at {REPO_URL}/blob/main/mycli/myclirc .  An
                    empty <value> is generally accepted.

                    To ignore all of this, set

                        [main]
                        my_cnf_transition_done = True

                    in ~/.myclirc.

                    --------

                    """
                ),
                err=True,
                fg='yellow',
            )

    mycli.connect(
        database=database,
        user=cli_args.user,
        passwd=cli_args.password,
        host=cli_args.host,
        port=cli_args.port,
        socket=cli_args.socket,
        local_infile=cli_args.local_infile,
        ssl=ssl,
        ssh_user=ssh_user,
        ssh_host=ssh_host,
        ssh_port=ssh_port,
        ssh_password=cli_args.ssh_password,
        ssh_key_filename=ssh_key_filename,
        init_command=combined_init_cmd,
        unbuffered=cli_args.unbuffered,
        character_set=cli_args.character_set,
        use_keyring=use_keyring,
        reset_keyring=reset_keyring,
        keepalive_ticks=keepalive_ticks,
    )

    if combined_init_cmd:
        click.echo(f"Executing init-command: {combined_init_cmd}", err=True)

    mycli.logger.debug(
        "Launch Params: \n\tdatabase: %r\tuser: %r\thost: %r\tport: %r",
        database,
        cli_args.user,
        cli_args.host,
        cli_args.port,
    )

    if cli_args.execute is not None:
        sys.exit(main_execute_from_cli(mycli, cli_args))

    if cli_args.batch is not None and cli_args.batch != '-' and cli_args.progress and sys.stderr.isatty():
        sys.exit(main_batch_with_progress_bar(mycli, cli_args))

    if cli_args.batch is not None:
        sys.exit(main_batch_without_progress_bar(mycli, cli_args))

    if not sys.stdin.isatty():
        sys.exit(main_batch_from_stdin(mycli, cli_args))

    mycli.run_cli()
    mycli.close()


def main() -> int | None:
    try:
        result = click_entrypoint.main(
            filtered_sys_argv(),
            standalone_mode=False,  # disable builtin exception handling
            prog_name='mycli',
        )
    except click.Abort:
        print('Aborted!', file=sys.stderr)
        sys.exit(1)
    except BrokenPipeError:
        sys.exit(1)
    except click.ClickException as e:
        e.show()
        if hasattr(e, 'exit_code'):
            sys.exit(e.exit_code)
        else:
            sys.exit(2)
    if result is None:
        return 0
    elif isinstance(result, int):
        return result
    else:
        return 1


if __name__ == "__main__":
    sys.exit(main())
