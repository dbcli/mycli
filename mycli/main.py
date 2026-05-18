from __future__ import annotations

import os
import sys

from cli_helpers.tabular_output import TabularOutputFormatter
from cli_helpers.tabular_output.output_formatter import MISSING_VALUE as DEFAULT_MISSING_VALUE
import click
import clickdc
import keyring
import pymysql
from pymysql.constants.CR import CR_SERVER_LOST
from pymysql.constants.ER import ACCESS_DENIED_ERROR, HANDSHAKE_ERROR

import mycli as mycli_package
from mycli.cli_args import EMPTY_PASSWORD_FLAG_SENTINEL, CliArgs
from mycli.cli_runner import run_from_cli_args
from mycli.client import MyCli
from mycli.clistyle import style_factory_helpers, style_factory_ptoolkit
from mycli.completion_refresher import CompletionRefresher
from mycli.config import get_mylogin_cnf_path, open_mylogin_cnf, read_config_files, str_to_bool, write_default_config
from mycli.constants import ER_MUST_CHANGE_PASSWORD_LOGIN
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
    'CliArgs',
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
