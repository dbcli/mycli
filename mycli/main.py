from __future__ import annotations

from dataclasses import dataclass
from io import TextIOWrapper
import os
import sys
from typing import Callable

from cli_helpers.tabular_output import TabularOutputFormatter
from cli_helpers.tabular_output.output_formatter import MISSING_VALUE as DEFAULT_MISSING_VALUE
import click
import clickdc
import keyring
import pymysql
from pymysql.constants.CR import CR_SERVER_LOST
from pymysql.constants.ER import ACCESS_DENIED_ERROR, HANDSHAKE_ERROR

import mycli as mycli_package
from mycli.cli_runner import run_from_cli_args
from mycli.client import MyCli
from mycli.clistyle import style_factory_helpers, style_factory_ptoolkit
from mycli.completion_refresher import CompletionRefresher
from mycli.config import get_mylogin_cnf_path, open_mylogin_cnf, read_config_files, str_to_bool, write_default_config
from mycli.constants import (
    DEFAULT_PROMPT,
    EMPTY_PASSWORD_FLAG_SENTINEL,
    ER_MUST_CHANGE_PASSWORD_LOGIN,
)
from mycli.main_modes.batch import main_batch_from_stdin, main_batch_with_progress_bar, main_batch_without_progress_bar
from mycli.main_modes.checkup import main_checkup
from mycli.main_modes.execute import main_execute_from_cli
from mycli.main_modes.list_dsn import main_list_dsn
from mycli.main_modes.list_ssh_config import main_list_ssh_config
from mycli.main_modes.repl import main_repl, set_all_external_titles
from mycli.packages import special
from mycli.packages.cli_utils import filtered_sys_argv, is_valid_connection_scheme
from mycli.packages.filepaths import dir_path_exists, guess_socket_location
from mycli.packages.interactive_utils import confirm_destructive_query
from mycli.packages.special.favoritequeries import FavoriteQueries
from mycli.packages.tabular_output import sql_format
from mycli.schema_prefetcher import SchemaPrefetcher
from mycli.sqlcompleter import SQLCompleter
from mycli.sqlexecute import SQLExecute
from mycli.types import Query

__all__ = [
    'ACCESS_DENIED_ERROR',
    'CR_SERVER_LOST',
    'DEFAULT_MISSING_VALUE',
    'EMPTY_PASSWORD_FLAG_SENTINEL',
    'ER_MUST_CHANGE_PASSWORD_LOGIN',
    'FavoriteQueries',
    'HANDSHAKE_ERROR',
    'MyCli',
    'Query',
    'SQLCompleter',
    'SQLExecute',
    'SchemaPrefetcher',
    'TabularOutputFormatter',
    'CompletionRefresher',
    'click_entrypoint',
    'confirm_destructive_query',
    'dir_path_exists',
    'filtered_sys_argv',
    'get_mylogin_cnf_path',
    'guess_socket_location',
    'is_valid_connection_scheme',
    'keyring',
    'main',
    'main_batch_from_stdin',
    'main_batch_with_progress_bar',
    'main_batch_without_progress_bar',
    'main_checkup',
    'main_execute_from_cli',
    'main_list_dsn',
    'main_list_ssh_config',
    'main_repl',
    'open_mylogin_cnf',
    'os',
    'pymysql',
    'read_config_files',
    'set_all_external_titles',
    'special',
    'sql_format',
    'str_to_bool',
    'style_factory_helpers',
    'style_factory_ptoolkit',
    'write_default_config',
]


class IntOrStringClickParamType(click.ParamType):
    name = 'text'  # display as TEXT in helpdoc

    def convert(self, value, param, ctx):
        if isinstance(value, int):
            return value
        elif isinstance(value, str):
            return value
        elif value is None:
            return value
        else:
            self.fail('Not a valid password string', param, ctx)


INT_OR_STRING_CLICK_TYPE = IntOrStringClickParamType()


@dataclass(slots=True)
class CliArgs:
    database: str | None = clickdc.argument(
        type=str,
        default=None,
        nargs=1,
    )
    host: str | None = clickdc.option(
        '-h',
        '--hostname',
        'host',
        type=str,
        envvar='MYSQL_HOST',
        help='Host address of the database.',
    )
    port: int | None = clickdc.option(
        '-P',
        type=int,
        envvar='MYSQL_TCP_PORT',
        help='Port number to use for connection. Honors $MYSQL_TCP_PORT.',
    )
    user: str | None = clickdc.option(
        '-u',
        '--user',
        '--username',
        'user',
        type=str,
        envvar='MYSQL_USER',
        help='User name to connect to the database.',
    )
    socket: str | None = clickdc.option(
        '-S',
        type=str,
        envvar='MYSQL_UNIX_SOCKET',
        help='The socket file to use for connection.',
    )
    password: int | str | None = clickdc.option(
        '-p',
        '--pass',
        '--password',
        'password',
        type=INT_OR_STRING_CLICK_TYPE,
        is_flag=False,
        flag_value=EMPTY_PASSWORD_FLAG_SENTINEL,
        help='Prompt for (or pass in cleartext) the password to connect to the database.',
    )
    password_file: str | None = clickdc.option(
        type=click.Path(),
        help='File or FIFO path containing the password to connect to the db if not specified otherwise.',
    )
    ssh_user: str | None = clickdc.option(
        type=str,
        help='User name to connect to ssh server.',
    )
    ssh_host: str | None = clickdc.option(
        type=str,
        help='Host name to connect to ssh server.',
    )
    ssh_port: int = clickdc.option(
        type=int,
        default=22,
        help='Port to connect to ssh server.',
    )
    ssh_password: str | None = clickdc.option(
        type=str,
        help='Password to connect to ssh server.',
    )
    ssh_key_filename: str | None = clickdc.option(
        type=str,
        help='Private key filename (identify file) for the ssh connection.',
    )
    ssh_config_path: str = clickdc.option(
        type=str,
        help='Path to ssh configuration.',
        default=os.path.expanduser('~') + '/.ssh/config',
    )
    ssh_config_host: str | None = clickdc.option(
        type=str,
        help='Host to connect to ssh server reading from ssh configuration.',
    )
    list_ssh_config: bool = clickdc.option(
        is_flag=True,
        help='list ssh configurations in the ssh config (requires paramiko).',
    )
    ssh_warning_off: bool = clickdc.option(
        is_flag=True,
        help='Suppress the SSH deprecation notice.',
    )
    ssl_mode: str = clickdc.option(
        type=click.Choice(['auto', 'on', 'off']),
        help='Set desired SSL behavior. auto=preferred if TCP/IP, on=required, off=off.',
    )
    deprecated_ssl: bool | None = clickdc.option(
        '--ssl/--no-ssl',
        'deprecated_ssl',
        default=None,
        clickdc=None,
        help='Enable SSL for connection (automatically enabled with other flags).',
    )
    ssl_ca: str | None = clickdc.option(
        type=click.Path(exists=True),
        help='CA file in PEM format.',
    )
    ssl_capath: str | None = clickdc.option(
        type=click.Path(exists=True, file_okay=False, dir_okay=True),
        help='CA directory.',
    )
    ssl_cert: str | None = clickdc.option(
        type=click.Path(exists=True),
        help='X509 cert in PEM format.',
    )
    ssl_key: str | None = clickdc.option(
        type=click.Path(exists=True),
        help='X509 key in PEM format.',
    )
    ssl_cipher: str | None = clickdc.option(
        type=str,
        help='SSL cipher to use.',
    )
    tls_version: str | None = clickdc.option(
        type=click.Choice(['TLSv1', 'TLSv1.1', 'TLSv1.2', 'TLSv1.3'], case_sensitive=False),
        help='TLS protocol version for secure connection.',
    )
    ssl_verify_server_cert: bool = clickdc.option(
        is_flag=True,
        help=("""Verify server's "Common Name" in its cert against hostname used when connecting. This option is disabled by default."""),
    )
    verbose: int = clickdc.option(
        '-v',
        count=True,
        help='More verbose output and feedback.  Can be given multiple times.',
    )
    quiet: bool = clickdc.option(
        '-q',
        is_flag=True,
        help='Less verbose output and feedback.',
    )
    dbname: str | None = clickdc.option(
        '-D',
        '--database',
        'dbname',
        type=str,
        clickdc=None,
        help='Database or DSN to use for the connection.',
    )
    dsn: str = clickdc.option(
        '-d',
        type=str,
        default='',
        envvar='MYSQL_DSN',
        help='DSN alias configured in the ~/.myclirc file, or a full DSN.',
    )
    list_dsn: bool = clickdc.option(
        is_flag=True,
        help='Show list of DSN aliases configured in the [alias_dsn] section of ~/.myclirc.',
    )
    prompt: str | None = clickdc.option(
        '-R',
        type=str,
        help=f'Prompt format (Default: "{DEFAULT_PROMPT}").',
    )
    toolbar: str | None = clickdc.option(
        type=str,
        help='Toolbar format.',
    )
    logfile: TextIOWrapper | None = clickdc.option(
        '-l',
        type=click.File(mode='a', encoding='utf-8'),
        help='Log every query and its results to a file.',
    )
    checkpoint: TextIOWrapper | None = clickdc.option(
        type=click.File(mode='a', encoding='utf-8'),
        help='In batch or --execute mode, log successful queries to a file, and skipped with --resume.',
    )
    resume: bool = clickdc.option(
        '--resume',
        is_flag=True,
        help='In batch mode, resume after replaying statements in the --checkpoint file.',
    )
    defaults_group_suffix: str | None = clickdc.option(
        type=str,
        help='Read MySQL config groups with the specified suffix.',
    )
    defaults_file: str | None = clickdc.option(
        type=click.Path(),
        help='Only read MySQL options from the given file.',
    )
    myclirc: str = clickdc.option(
        type=click.Path(),
        default='~/.myclirc',
        help='Location of myclirc file.',
    )
    auto_vertical_output: bool = clickdc.option(
        is_flag=True,
        help='Automatically switch to vertical output mode if the result is wider than the terminal width.',
    )
    show_warnings: bool | None = clickdc.option(
        '--show-warnings/--no-show-warnings',
        is_flag=True,
        default=None,
        clickdc=None,
        help='Automatically show warnings after executing a SQL statement.',
    )
    table: bool = clickdc.option(
        '-t',
        is_flag=True,
        help='Shorthand for --format=table.',
    )
    csv: bool = clickdc.option(
        is_flag=True,
        help='Shorthand for --format=csv.',
    )
    warn: bool | None = clickdc.option(
        '--warn/--no-warn',
        default=None,
        clickdc=None,
        help='Warn before running a destructive query.',
    )
    local_infile: bool | None = clickdc.option(
        type=bool,
        is_flag=False,
        default=None,
        help='Enable/disable LOAD DATA LOCAL INFILE.',
    )
    login_path: str | None = clickdc.option(
        '-g',
        type=str,
        help='Read this path from the login file.',
    )
    execute: str | None = clickdc.option(
        '-e',
        type=str,
        help='Execute command and quit.',
    )
    init_command: str | None = clickdc.option(
        type=str,
        help='SQL statement to execute after connecting.',
    )
    unbuffered: bool | None = clickdc.option(
        is_flag=True,
        help='Instead of copying every row of data into a buffer, fetch rows as needed, to save memory.',
    )
    character_set: str | None = clickdc.option(
        '--charset',
        '--character-set',
        'character_set',
        type=str,
        help='Character set for MySQL session.',
    )
    batch: str | None = clickdc.option(
        type=str,
        help='SQL script to execute in batch mode.',
    )
    noninteractive: bool = clickdc.option(
        is_flag=True,
        help="Don't prompt during batch input.  Recommended.",
    )
    format: str | None = clickdc.option(
        type=click.Choice(['default', 'csv', 'tsv', 'table']),
        help='Format for batch or --execute output.',
    )
    throttle: float = clickdc.option(
        type=float,
        default=0.0,
        help='Pause in seconds between queries in batch mode.',
    )
    progress: bool = clickdc.option(
        is_flag=True,
        help='Show progress on the standard error with --batch.',
    )
    use_keyring: str | None = clickdc.option(
        type=click.Choice(['true', 'false', 'reset']),
        default=None,
        help='Store and retrieve passwords from the system keyring: true/false/reset.',
    )
    keepalive_ticks: int | None = clickdc.option(
        type=int,
        help='Send regular keepalive pings to the connection, roughly every <int> seconds.',
    )
    checkup: bool = clickdc.option(
        is_flag=True,
        help='Run a checkup on your configuration.',
    )


def get_password_from_file(password_file: str | None) -> str | None:
    if not password_file:
        return None
    try:
        with open(password_file) as fp:
            return fp.readline().removesuffix('\n')
    except FileNotFoundError:
        click.secho(f"Password file '{password_file}' not found", err=True, fg='red')
        sys.exit(1)
    except PermissionError:
        click.secho(f"Permission denied reading password file '{password_file}'", err=True, fg='red')
        sys.exit(1)
    except IsADirectoryError:
        click.secho(f"Path '{password_file}' is a directory, not a file", err=True, fg='red')
        sys.exit(1)
    except Exception as e:
        click.secho(f"Error reading password file '{password_file}': {str(e)}", err=True, fg='red')
        sys.exit(1)


def preprocess_cli_args(
    cli_args: CliArgs,
    is_valid_connection_scheme: Callable[[str], tuple[bool, str | None]],
) -> int:
    if cli_args.database is None and isinstance(cli_args.password, str) and '://' in cli_args.password:
        is_valid_scheme, scheme = is_valid_connection_scheme(cli_args.password)
        if not is_valid_scheme:
            click.secho(f'Error: Unknown connection scheme provided for DSN URI ({scheme}://)', err=True, fg='red')
            sys.exit(1)
        cli_args.database = cli_args.password
        cli_args.password = EMPTY_PASSWORD_FLAG_SENTINEL

    if cli_args.password is None and cli_args.password_file:
        password_from_file = get_password_from_file(cli_args.password_file)
        if password_from_file is not None:
            cli_args.password = password_from_file

    if cli_args.password is None and os.environ.get('MYSQL_PWD') is not None:
        cli_args.password = os.environ.get('MYSQL_PWD')

    if cli_args.resume and not cli_args.checkpoint:
        click.secho('Error: --resume requires a --checkpoint file.', err=True, fg='red')
        sys.exit(1)

    if cli_args.resume and not cli_args.batch:
        click.secho('Error: --resume requires a --batch file.', err=True, fg='red')
        sys.exit(1)

    if cli_args.verbose and cli_args.quiet:
        click.secho('Error: --verbose and --quiet are incompatible.', err=True, fg='red')
        sys.exit(1)
    elif cli_args.verbose:
        return int(cli_args.verbose)
    elif cli_args.quiet:
        return -1
    return 0


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

    run_from_cli_args(cli_args, client_factory=MyCli)


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
