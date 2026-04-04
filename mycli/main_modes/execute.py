from __future__ import annotations

import sys
from typing import TYPE_CHECKING

import click

if TYPE_CHECKING:
    from mycli.main import CliArgs, MyCli


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

        mycli.run_query(execute_sql, checkpoint=cli_args.checkpoint)
        return 0
    except Exception as e:
        click.secho(str(e), err=True, fg="red")
        return 1
