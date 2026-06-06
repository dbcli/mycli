from __future__ import annotations

from collections.abc import Generator, Iterable
import logging
import os
import re
from typing import TYPE_CHECKING, Any, cast

import click

from mycli.main_modes.repl import set_all_external_titles
from mycli.packages import special
from mycli.packages.filepaths import dir_path_exists
from mycli.packages.interactive_utils import confirm_destructive_query
from mycli.packages.special.main import ArgType, SpecialCommandAlias
from mycli.packages.sqlresult import SQLResult
from mycli.sqlexecute import SQLExecute


class ClientCommandsMixin:
    if TYPE_CHECKING:
        main_formatter: Any
        redirect_formatter: Any
        sqlexecute: Any
        destructive_warning: bool
        destructive_keywords: Any
        config: Any
        prompt_format: str

        def refresh_completions(self, reset: bool = False) -> list[SQLResult]: ...
        def reconnect(self, database: str = '') -> bool: ...
        def echo(self, *args: Any, **kwargs: Any) -> None: ...

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
        set_all_external_titles(cast(Any, self))

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
