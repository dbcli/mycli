from __future__ import annotations

from io import TextIOWrapper
import logging
import os
import threading
from typing import IO, Literal

from cli_helpers.tabular_output import TabularOutputFormatter
from configobj import ConfigObj
from prompt_toolkit.formatted_text import to_formatted_text
from prompt_toolkit.shortcuts import PromptSession
import sqlparse

from mycli.app_state import (
    AppStateMixin,
    configure_prompt_state,
    destructive_keywords_from_config,
    llm_prompt_truncation,
    normalize_ssl_mode,
)
from mycli.client_commands import ClientCommandsMixin
from mycli.client_connection import ClientConnectionMixin
from mycli.client_query import ClientQueryMixin
from mycli.clistyle import style_factory_helpers, style_factory_ptoolkit
from mycli.completion_refresher import CompletionRefresher
from mycli.config import (
    get_mylogin_cnf_path,
    open_mylogin_cnf,
    read_config_file,
    read_config_files,
    write_default_config,
)
from mycli.constants import DEFAULT_PROMPT
from mycli.main_modes import repl as repl_package
from mycli.output import OutputMixin
from mycli.packages import special
from mycli.packages.special.dsn_aliases import DsnAliases
from mycli.packages.special.favoritequeries import FavoriteQueries
from mycli.packages.tabular_output import sql_format
from mycli.schema_prefetcher import SchemaPrefetcher
from mycli.sqlcompleter import SQLCompleter
from mycli.sqlexecute import SQLExecute
from mycli.ssh_tunnel import SshTunnel
from mycli.types import Query

sqlparse.engine.grouping.MAX_GROUPING_DEPTH = None  # type: ignore[assignment]
sqlparse.engine.grouping.MAX_GROUPING_TOKENS = None  # type: ignore[assignment]


class MyCli(AppStateMixin, OutputMixin, ClientCommandsMixin, ClientConnectionMixin, ClientQueryMixin):
    default_prompt = DEFAULT_PROMPT
    default_prompt_splitln = "\\u@\\h\\n(\\t):\\d>"
    max_len_prompt = 45
    prompt_lines: int
    sqlexecute: SQLExecute | None
    numeric_alignment: str

    # check XDG_CONFIG_HOME exists and not an empty string
    xdg_config_home = os.environ.get("XDG_CONFIG_HOME", "~/.config")
    system_config_files: list[str | IO[str]] = [
        "/etc/myclirc",
        os.path.join(os.path.expanduser(xdg_config_home), "mycli", "myclirc"),
    ]

    def __init__(
        self,
        sqlexecute: SQLExecute | None = None,
        prompt: str | None = None,
        toolbar_format: str | None = None,
        logfile: TextIOWrapper | Literal[False] | None = None,
        login_path: str | None = None,
        auto_vertical_output: bool = False,
        warn: bool | None = None,
        myclirc: str = "~/.myclirc",
        show_warnings: bool | None = None,
        cli_verbosity: int = 0,
    ) -> None:
        self.sqlexecute = sqlexecute
        self.ssh_tunnel: SshTunnel | None = None
        self.logfile = logfile
        self.login_path = login_path
        self.toolbar_error_message: str | None = None
        self.prompt_session: PromptSession | None = None
        self._keepalive_counter = 0
        self.keepalive_ticks: int | None = 0
        self.sandbox_mode: bool = False
        self.checkpoint: IO | None = None

        # Load config.
        config_files: list[str | IO[str]] = self.system_config_files + [myclirc]

        c = self.config = read_config_files(config_files)
        # only needed in --checkup mode. todo: only load when needed
        self.config_without_package_defaults = read_config_files(config_files, ignore_package_defaults=True)
        # only needed in --checkup mode. todo: only load when needed
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
        DsnAliases.instance = DsnAliases.from_config(self.config)

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
        self.numeric_alignment = c['main'].get('numeric_alignment', 'right') or 'right'
        self.binary_display = c['main'].get('binary_display')
        self.llm_prompt_field_truncate, self.llm_prompt_section_truncate = llm_prompt_truncation(c)

        self.ssl_mode, ssl_mode_error = normalize_ssl_mode(c, self.config_without_package_defaults)
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
        self.mylogin_cnf = ConfigObj()
        mylogin_cnf_h = None
        if mylogin_cnf_path := get_mylogin_cnf_path():
            mylogin_cnf_h = open_mylogin_cnf(mylogin_cnf_path)
            if mylogin_cnf_h:
                self.mylogin_cnf = read_config_file(mylogin_cnf_h, list_values=False) or ConfigObj()
            else:
                print("Error: Unable to read login path file.")

        configure_prompt_state(self, c, prompt, toolbar_format)
        self.prompt_session = None
        self.destructive_keywords = destructive_keywords_from_config(c)
        special.set_destructive_keywords(self.destructive_keywords)

    def close(self) -> None:
        try:
            self.schema_prefetcher.stop()
        except Exception:
            pass
        if self.sqlexecute is not None:
            try:
                self.sqlexecute.close()
            except Exception:
                pass
        if self.ssh_tunnel is not None:
            try:
                self.ssh_tunnel.close()
            except Exception:
                pass

    def run_cli(self) -> None:
        repl_package.main_repl(self)
