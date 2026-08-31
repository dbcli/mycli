from __future__ import annotations

from collections.abc import Generator, Mapping
import logging
import os
import re
import shlex
from typing import TYPE_CHECKING, Any, cast

import click
import sqlparse

from mycli.compat import WIN
from mycli.config import write_default_config
from mycli.main_modes.repl import set_all_external_titles
from mycli.packages import special
from mycli.packages.batch_utils import statements_from_filehandle
from mycli.packages.filepaths import dir_path_exists
from mycli.packages.interactive_utils import confirm_destructive_query
from mycli.packages.ptoolkit.history import FileHistoryWithTimestamp
from mycli.packages.special import main as special_main
from mycli.packages.special.iocommands import expand_favorite_query
from mycli.packages.special.main import ArgType, SpecialCommandAlias
from mycli.packages.sqlresult import SQLResult
from mycli.sqlexecute import SQLExecute

CONFIG_COMMAND_USAGE = '''Syntax:
  /config get <key>
  /config search <regex>
  /config edit
Examples:
  /config get main.show_warnings
  /config search warning
  /config edit'''
MISSING_CONFIG_VALUE = object()
DSN_CONFIG_VALUE = object()
FAVORITES_CONFIG_VALUE = object()
HIDDEN_CONFIG_SECTIONS = frozenset({'alias_dsn', 'favorite_queries'})
INVALID_SOURCE_FILENAME = 'Source accepts exactly one filename; filenames containing spaces must be quoted.'
SOURCE_SAFE_SPECIAL_COMMANDS = frozenset({
    'connect',
    'fd',
    'fs',
    'help',
    'l',
    'nowarnings',
    'ping',
    'prompt',
    'redirectformat',
    'rehash',
    'status',
    'tableformat',
    'timing',
    'use',
    'warnings',
    'dt',
})
SOURCE_SAFE_SUBCOMMANDS = {
    'config': frozenset({'help', 'get', 'search'}),
    'dsn': frozenset({'help', 'list', 'show', 'save', 'delete'}),
    'favorite': frozenset({'help', 'list', 'reload', 'run', 'save', 'delete'}),
}


def _render_config_value(value: Any) -> str:
    if isinstance(value, list):
        return ', '.join(str(item) for item in value)
    return str(value)


def _parse_source_arguments(arg: str) -> tuple[str, bool, bool, bool]:
    allow_special = False
    show_queries = False
    page_output = False
    filename = arg
    while arguments := filename.split(maxsplit=1):
        if arguments[0] == '--special':
            allow_special = True
        elif arguments[0] == '--show':
            show_queries = True
        elif arguments[0] == '--page':
            page_output = True
        else:
            break
        filename = arguments[1] if len(arguments) == 2 else ''
    return filename, allow_special, show_queries, page_output


def _has_unquoted_whitespace(value: str) -> bool:
    quote: str | None = None
    escaped = False
    for character in value:
        if escaped:
            if quote is None and character.isspace():
                return True
            escaped = False
            continue
        if not WIN and character == '\\' and quote != "'":
            escaped = True
            continue
        if character in ("'", '"'):
            if quote is None:
                quote = character
            elif quote == character:
                quote = None
        elif quote is None and character.isspace():
            return True
    return False


def _parse_source_filename(filename: str) -> str:
    if not filename:
        return ''
    if _has_unquoted_whitespace(filename):
        raise ValueError(INVALID_SOURCE_FILENAME)
    try:
        arguments = shlex.split(filename, posix=not WIN)
    except ValueError as error:
        raise ValueError(f'Invalid source filename: {error}.') from None
    if len(arguments) != 1:
        raise ValueError(INVALID_SOURCE_FILENAME)
    parsed_filename = arguments[0]
    if WIN and len(parsed_filename) >= 2 and parsed_filename[0] == parsed_filename[-1] and parsed_filename[0] in ("'", '"'):
        parsed_filename = parsed_filename[1:-1]
    return parsed_filename


def _registered_special_command(query: str) -> tuple[str, str] | None:
    command, _verbosity, arg = special.parse_special_command(query)
    registered = special_main.COMMANDS.get(command)
    if registered is None:
        registered = special_main.COMMANDS.get(command.lower())
    if registered is None:
        return None
    return registered.command.removeprefix('\\').removeprefix('/').lower(), arg


def _favorite_source_command_is_safe(arg: str) -> bool:
    query, _error = expand_favorite_query(arg)
    if query is None:
        return True
    return not any(special.is_special_command(statement.rstrip(';')) for statement in sqlparse.split(query))


def _source_special_command_is_safe(query: str) -> bool:
    parsed = _registered_special_command(query)
    if parsed is None:
        return False

    command, arg = parsed
    if command == 'f':
        return not arg or _favorite_source_command_is_safe(arg)
    if command in ('fd', 'fs'):
        return True
    if command in SOURCE_SAFE_SPECIAL_COMMANDS:
        return True

    subcommands = SOURCE_SAFE_SUBCOMMANDS.get(command)
    if subcommands is None:
        return False
    arguments = arg.split(maxsplit=1)
    subcommand = arguments[0].lower() if arguments else 'help'
    if subcommand not in subcommands:
        return False
    if command == 'favorite' and subcommand == 'run':
        run_arg = arguments[1] if len(arguments) == 2 else ''
        return not run_arg or _favorite_source_command_is_safe(run_arg)
    return True


def _iter_config_values(
    config: Mapping[str, Any],
    prefix: str = '',
) -> Generator[tuple[str, str], None, None]:
    """Yield dotted paths and rendered values for searchable settings."""
    for key, value in config.items():
        if not prefix and key in HIDDEN_CONFIG_SECTIONS:
            continue

        path = f'{prefix}.{key}' if prefix else key
        if isinstance(value, Mapping):
            yield from _iter_config_values(value, path)
        else:
            yield path, _render_config_value(value)


def get_config_property_names(config: Mapping[str, Any]) -> list[str]:
    """Return sorted leaf paths available to the config command."""
    return sorted(path for path, _value in _iter_config_values(config))


def _resolve_config_path(config: Mapping[str, Any], path: str) -> Any:
    """Resolve a dotted path while allowing dots within mapping keys."""
    parts = path.split('.')
    value: Any = config
    top_level = True
    while parts:
        if not isinstance(value, Mapping):
            return MISSING_CONFIG_VALUE

        for part_count in range(len(parts), 0, -1):
            key = '.'.join(parts[:part_count])
            if key in value:
                if top_level and key == 'alias_dsn':
                    return DSN_CONFIG_VALUE
                if top_level and key == 'favorite_queries':
                    return FAVORITES_CONFIG_VALUE
                value = value[key]
                parts = parts[part_count:]
                top_level = False
                break
        else:
            return MISSING_CONFIG_VALUE

    return value


class ClientCommandsMixin:
    if TYPE_CHECKING:
        main_formatter: Any
        redirect_formatter: Any
        sqlexecute: Any
        destructive_warning: bool
        destructive_keywords: Any
        config: Any
        myclirc_path: str
        prompt_session: Any
        prompt_format: str

        def refresh_completions(self, reset: bool = False) -> list[SQLResult]: ...
        def reconnect(self, database: str = '') -> bool: ...
        def echo(self, *args: Any, **kwargs: Any) -> None: ...

    def register_special_commands(self) -> None:
        special.register_special_command(
            self.change_db,
            "use",
            "/use <database>",
            "Change to a new database.",
            aliases=[SpecialCommandAlias("\\u", case_sensitive=False)],
            completion_snippet='change databases',
        )
        special.register_special_command(
            self.manual_reconnect,
            "connect",
            "/connect [database]",
            "Reconnect to the server, optionally switching databases.",
            case_sensitive=True,
            aliases=[SpecialCommandAlias("\\r", case_sensitive=True)],
            completion_snippet='reconnect to server',
        )
        special.register_special_command(
            self.rehash,
            "rehash",
            "/rehash",
            "Refresh auto-completions.",
            arg_type=ArgType.NO_ARGUMENT,
            aliases=[SpecialCommandAlias("\\#", case_sensitive=False)],
            completion_snippet='refresh completions',
        )
        special.register_special_command(
            self.change_table_format,
            "tableformat",
            "/tableformat <format>",
            "Change the table format used to output interactive results.",
            case_sensitive=True,
            aliases=[SpecialCommandAlias("\\T", case_sensitive=True)],
            completion_snippet='change interactive output format',
        )
        special.register_special_command(
            self.change_redirect_format,
            "redirectformat",
            "/redirectformat <format>",
            "Change the table format used to output redirected results.",
            case_sensitive=True,
            aliases=[SpecialCommandAlias("\\Tr", case_sensitive=True)],
            completion_snippet='change redirected output format',
        )
        special.register_special_command(
            self.execute_from_file,
            "source",
            "/source [--special|--show|--page] <file>",
            "Execute queries from a file.",
            aliases=[SpecialCommandAlias("\\.", case_sensitive=False)],
            completion_snippet='execute queries from file',
        )
        special.register_special_command(
            self.change_prompt_format,
            "prompt",
            "/prompt [string]",
            "Show or change prompt format.",
            case_sensitive=True,
            aliases=[SpecialCommandAlias("\\R", case_sensitive=True)],
            completion_snippet='show or change prompt format',
        )
        special.register_special_command(
            self.config_command,
            r'\config',
            '/config <help|get|search|edit> [key]',
            'Inspect settings from config files.',
            completion_snippet='inspect config file settings',
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

    def rehash(self) -> list[SQLResult]:
        prompt_session = getattr(self, 'prompt_session', None)
        history = getattr(prompt_session, 'history', None)
        if isinstance(history, FileHistoryWithTimestamp):
            history.refresh_frecency()
        return self.refresh_completions()

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

    def config_command(self, arg: str, **_) -> list[SQLResult]:
        args = arg.strip().split(maxsplit=1)
        if not args or args[0].lower() == 'help':
            return [SQLResult(preamble=CONFIG_COMMAND_USAGE)]

        subcommand = args[0].lower()
        if subcommand == 'edit' and len(args) == 1:
            return self.edit_config_file()

        if subcommand == 'get' and len(args) == 2 and len(args[1].split()) == 1:
            path = args[1]
            value = _resolve_config_path(self.config, path)
            if value is MISSING_CONFIG_VALUE:
                return [SQLResult(status=f'Config key not found: {path}.')]
            if value is DSN_CONFIG_VALUE:
                return [SQLResult(status='See "/dsn list" for DSNs.')]
            if value is FAVORITES_CONFIG_VALUE:
                return [SQLResult(status='See "/f" for favorite queries.')]
            if isinstance(value, Mapping):
                return [SQLResult(status=f'Config path is not a value: {path}.')]
            return [SQLResult(header=['Key', 'Value'], rows=[(path, _render_config_value(value))])]

        if subcommand == 'search' and len(args) == 2:
            pattern_text = args[1]
            try:
                pattern = re.compile(pattern_text, re.IGNORECASE)
            except re.error as error:
                return [SQLResult(status=f'Invalid regular expression: {error}.')]

            rows = sorted(
                (path, value) for path, value in _iter_config_values(self.config) if pattern.search(path) or pattern.search(value)
            )
            if not rows:
                return [SQLResult(status=f'No configuration values match "{pattern_text}".')]
            return [SQLResult(header=['Key', 'Value'], rows=rows)]

        return [SQLResult(preamble=CONFIG_COMMAND_USAGE)]

    def edit_config_file(self) -> list[SQLResult]:
        try:
            write_default_config(self.myclirc_path, overwrite=False)
            click.edit(filename=self.myclirc_path)
        except KeyboardInterrupt:
            return [SQLResult(status='Config edit cancelled.')]
        except (click.ClickException, OSError) as error:
            return [SQLResult(status=f'Unable to edit config file "{self.myclirc_path}": {error}')]
        return [SQLResult(status=f'Config file edited: {self.myclirc_path}. Restart mycli to apply changes.')]

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

    def execute_from_file(self, arg: str, **_) -> Generator[SQLResult, None, None]:
        filename, allow_special, show_queries, page_output = _parse_source_arguments(arg)
        if page_output:
            yield SQLResult(command={'name': 'source_page'})
        try:
            filename = _parse_source_filename(filename)
        except ValueError as error:
            yield SQLResult(status=str(error), is_error=True)
            return
        if not filename:
            yield SQLResult(status="Missing required argument: filename.", is_error=True)
            return

        try:
            file_h = open(os.path.expanduser(filename))
        except OSError as error:
            yield SQLResult(status=str(error))
            return

        assert isinstance(self.sqlexecute, SQLExecute)
        with file_h:
            statements = statements_from_filehandle(file_h)
            while True:
                try:
                    query, _counter = next(statements)
                except StopIteration:
                    return
                except (OSError, ValueError) as error:
                    yield SQLResult(status=str(error))
                    return

                special_query = query.rstrip(';')
                if special.is_special_command(special_query):
                    if not allow_special:
                        yield SQLResult(
                            status='Special commands are not supported without /source --special.',
                            is_error=True,
                        )
                        return
                    if not _source_special_command_is_safe(special_query):
                        command, _verbosity, _arg = special.parse_special_command(special_query)
                        yield SQLResult(
                            status=f'Special command is never permitted in source files: {command}.',
                            is_error=True,
                        )
                        return
                    if show_queries:
                        if page_output:
                            yield SQLResult(command={'name': 'source_show', 'text': special_query})
                        else:
                            click.secho(f'> {special_query}')
                    yield from self.sqlexecute.run(special_query)
                    continue

                if self.destructive_warning and confirm_destructive_query(self.destructive_keywords, query) is False:
                    continue
                if show_queries:
                    if page_output:
                        yield SQLResult(command={'name': 'source_show', 'text': query})
                    else:
                        click.secho(f'> {query}')
                yield from self.sqlexecute.run(query)

    def change_prompt_format(self, arg: str, **_) -> list[SQLResult]:
        """
        Show or change the prompt format.
        """
        if not arg:
            return [SQLResult(status=f'Prompt format: "{self.prompt_format}"')]

        if len(arg) >= 2 and arg[0] == arg[-1] and arg[0] in {"'", '"'}:
            arg = arg[1:-1]

        self.prompt_format = arg
        return [SQLResult(status=f'Changed prompt format to: "{arg}"')]

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
