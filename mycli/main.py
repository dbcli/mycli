from __future__ import annotations

from dataclasses import dataclass
from io import TextIOWrapper
import os
import sys
from textwrap import dedent
from typing import Callable

import click
import clickdc

import mycli as mycli_package
from mycli.cli_runner import run_from_cli_args
from mycli.client import MyCli
from mycli.constants import (
    DEFAULT_PROMPT,
    EMPTY_PASSWORD_FLAG_SENTINEL,
)
from mycli.packages.cli_utils import filtered_sys_argv


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
        help=dedent(
            """Password to connect to the database.
            Use with a value to set the password at the CLI, or alone in the last position to request a prompt.
            """
        ),
    )
    password_file: str | None = clickdc.option(
        type=click.Path(),
        help='File or FIFO path containing the password to connect to the db if not specified otherwise.',
    )
    ssl_mode: str = clickdc.option(
        type=click.Choice(['auto', 'on', 'off']),
        help='Set desired SSL behavior. auto=preferred if TCP/IP, on=required, off=off.',
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
    checkpoint: str | None = clickdc.option(
        type=str,
        help='In batch or --execute mode, log successful queries to a file, and skip them with --resume.',
    )
    resume: bool = clickdc.option(
        '--resume',
        is_flag=True,
        help='In batch mode, resume after replaying statements in the --checkpoint file.',
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
    warn_batch: bool = clickdc.option(
        is_flag=True,
        help='Warn before running a destructive query when executing a script.',
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
    # deprecated 2026-06-20
    noninteractive: bool = clickdc.option(
        is_flag=True,
        hidden=True,
        deprecated='See --warn-batch.',
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
        type=click.Choice(['auto', 'true', 'false', 'reset']),
        default=None,
        help='Store and retrieve passwords from the system keyring. auto means true, unless within an SSH connection.',
    )
    keepalive_ticks: int | None = clickdc.option(
        type=int,
        help='Send regular keepalive pings to the connection, roughly every <int> seconds.',
    )
    ssh_jump: str | None = clickdc.option(
        type=str,
        help='Open an SSH tunnel via [user@]host[:port] and connect to MySQL through it.',
    )
    checkup: bool = clickdc.option(
        is_flag=True,
        help='Run a checkup on your configuration.',
    )
    # hidden options which have no effect as of mycli 2.0.0, 2026-07.
    # todo: remove the hidden options, since they are still advertised
    # in spelling corrections.
    ssl: bool | None = clickdc.option(
        '--ssl/--no-ssl',
        clickdc=None,
        hidden=True,
        deprecated='No effect. See --ssl-mode.',
    )
    ssh_user: str | None = clickdc.option(
        type=str,
        hidden=True,
        deprecated='No effect. See --ssh-jump.',
    )
    ssh_host: str | None = clickdc.option(
        type=str,
        hidden=True,
        deprecated='No effect. See --ssh-jump.',
    )
    ssh_port: int = clickdc.option(
        type=int,
        hidden=True,
        deprecated='No effect. See --ssh-jump.',
    )
    ssh_password: str | None = clickdc.option(
        type=str,
        hidden=True,
        deprecated='No effect. See --ssh-jump.',
    )
    ssh_key_filename: str | None = clickdc.option(
        type=str,
        hidden=True,
        deprecated='No effect. See --ssh-jump.',
    )
    ssh_config_path: str = clickdc.option(
        type=str,
        hidden=True,
        deprecated='No effect. See --ssh-jump.',
    )
    ssh_config_host: str | None = clickdc.option(
        type=str,
        hidden=True,
        deprecated='No effect. See --ssh-jump.',
    )
    list_ssh_config: bool = clickdc.option(
        is_flag=True,
        hidden=True,
        deprecated='No effect. See --ssh-jump.',
    )
    ssh_warning_off: bool = clickdc.option(
        is_flag=True,
        hidden=True,
        deprecated='No effect. See --ssh-jump.',
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

    if (
        cli_args.checkpoint
        and os.path.exists(cli_args.checkpoint)
        and cli_args.batch
        and cli_args.batch != '-'
        and os.path.exists(cli_args.batch)
    ):
        if os.path.samefile(cli_args.batch, cli_args.checkpoint):
            click.secho('Error: --batch and --checkpoint must be different files.', err=True, fg='red')
            sys.exit(1)

    if (
        cli_args.logfile
        and os.path.exists(cli_args.logfile.name)
        and cli_args.batch
        and cli_args.batch != '-'
        and os.path.exists(cli_args.batch)
    ):
        if os.path.samefile(cli_args.batch, cli_args.logfile.name):
            click.secho('Error: --batch and --logfile must be different files.', err=True, fg='red')
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
            filtered_sys_argv(),  # type: ignore[arg-type]
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
