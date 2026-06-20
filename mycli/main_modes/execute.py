from __future__ import annotations

import sys
from typing import TYPE_CHECKING

import click

from mycli.packages.interactive_utils import confirm_destructive_query
from mycli.packages.sql_utils import is_destructive

if TYPE_CHECKING:
    from mycli.client import MyCli
    from mycli.main import CliArgs


def main_execute_from_cli(mycli: 'MyCli', cli_args: 'CliArgs') -> int:
    if cli_args.execute is None:
        return 1
    if not sys.stdin.isatty():
        click.secho('Ignoring STDIN since --execute was also given.', err=True, fg='red')
    if cli_args.batch:
        click.secho('Ignoring --batch since --execute was also given.', err=True, fg='red')
    try:
        execute_sql = cli_args.execute
        if cli_args.format == 'csv':
            mycli.main_formatter.format_name = 'csv'
            if execute_sql.endswith(r'\G'):
                execute_sql = execute_sql[:-2]
        elif cli_args.format == 'tsv':
            mycli.main_formatter.format_name = 'tsv'
            if execute_sql.endswith(r'\G'):
                execute_sql = execute_sql[:-2]
        elif cli_args.format == 'table':
            mycli.main_formatter.format_name = 'ascii'
            if execute_sql.endswith(r'\G'):
                execute_sql = execute_sql[:-2]
        else:
            mycli.main_formatter.format_name = 'tsv'

        execution_confirmed: bool | None = True
        if cli_args.warn_batch and is_destructive(mycli.destructive_keywords, execute_sql):
            try:
                sys.stdin = open('/dev/tty')
                execution_confirmed = confirm_destructive_query(mycli.destructive_keywords, execute_sql)
            except (IOError, OSError) as e:
                mycli.logger.warning('Unable to open TTY as stdin.')
                raise e
        if execution_confirmed:
            mycli.run_query(execute_sql, checkpoint=cli_args.checkpoint)
            return 0
        else:
            return 1
    except Exception as e:
        click.secho(str(e), err=True, fg="red")
        return 1
