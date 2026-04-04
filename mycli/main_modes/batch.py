from __future__ import annotations

import os
import sys
import time
from typing import TYPE_CHECKING

import click
import prompt_toolkit
from prompt_toolkit.shortcuts import ProgressBar
from prompt_toolkit.shortcuts.progress_bar import formatters as progress_bar_formatters
import pymysql

from mycli.packages.batch_utils import statements_from_filehandle
from mycli.packages.prompt_utils import confirm_destructive_query
from mycli.packages.sql_utils import is_destructive

if TYPE_CHECKING:
    from mycli.main import CliArgs, MyCli


def dispatch_batch_statements(
    mycli: 'MyCli',
    cli_args: 'CliArgs',
    statements: str,
    batch_counter: int,
) -> None:
    if batch_counter:
        if cli_args.format == 'csv':
            mycli.main_formatter.format_name = 'csv-noheader'
        elif cli_args.format == 'tsv':
            mycli.main_formatter.format_name = 'tsv_noheader'
        elif cli_args.format == 'table':
            mycli.main_formatter.format_name = 'ascii'
        else:
            mycli.main_formatter.format_name = 'tsv'
    else:
        if cli_args.format == 'csv':
            mycli.main_formatter.format_name = 'csv'
        elif cli_args.format == 'tsv':
            mycli.main_formatter.format_name = 'tsv'
        elif cli_args.format == 'table':
            mycli.main_formatter.format_name = 'ascii'
        else:
            mycli.main_formatter.format_name = 'tsv'

    warn_confirmed: bool | None = True
    if not cli_args.noninteractive and mycli.destructive_warning and is_destructive(mycli.destructive_keywords, statements):
        try:
            # this seems to work, even though we are reading from stdin above
            sys.stdin = open('/dev/tty')
            # bug: the prompt will not be visible if stdout is redirected
            warn_confirmed = confirm_destructive_query(mycli.destructive_keywords, statements)
        except (IOError, OSError) as e:
            mycli.logger.warning('Unable to open TTY as stdin.')
            raise e
    if warn_confirmed:
        if cli_args.throttle > 0 and batch_counter >= 1:
            time.sleep(cli_args.throttle)
        mycli.run_query(statements, checkpoint=cli_args.checkpoint, new_line=True)


def main_batch_with_progress_bar(mycli: 'MyCli', cli_args: 'CliArgs') -> int:
    goal_statements = 0
    if cli_args.batch is None:
        return 1
    if not sys.stdin.isatty() and cli_args.batch != '-':
        click.secho('Ignoring STDIN since --batch was also given.', err=True, fg='yellow')
    if os.path.exists(cli_args.batch) and not os.path.isfile(cli_args.batch):
        click.secho('--progress is only compatible with a plain file.', err=True, fg='red')
        return 1
    try:
        batch_count_h = click.open_file(cli_args.batch)
        for _statement, _counter in statements_from_filehandle(batch_count_h):
            goal_statements += 1
        batch_count_h.close()
        batch_h = click.open_file(cli_args.batch)
        batch_gen = statements_from_filehandle(batch_h)
    except (OSError, FileNotFoundError):
        click.secho(f'Failed to open --batch file: {cli_args.batch}', err=True, fg='red')
        return 1
    except ValueError as e:
        click.secho(f'Error reading --batch file: {cli_args.batch}: {e}', err=True, fg='red')
        return 1
    try:
        if goal_statements:
            pb_style = prompt_toolkit.styles.Style.from_dict({'bar-a': 'reverse'})
            custom_formatters = [
                progress_bar_formatters.Bar(start='[', end=']', sym_a=' ', sym_b=' ', sym_c=' '),
                progress_bar_formatters.Text(' '),
                progress_bar_formatters.Progress(),
                progress_bar_formatters.Text(' '),
                progress_bar_formatters.Text('eta ', style='class:time-left'),
                progress_bar_formatters.TimeLeft(),
                progress_bar_formatters.Text(' ', style='class:time-left'),
            ]
            err_output = prompt_toolkit.output.create_output(stdout=sys.stderr, always_prefer_tty=True)
            with ProgressBar(style=pb_style, formatters=custom_formatters, output=err_output) as pb:
                for _pb_counter in pb(range(goal_statements)):
                    statement, statement_counter = next(batch_gen)
                    dispatch_batch_statements(mycli, cli_args, statement, statement_counter)
    except (ValueError, StopIteration, IOError, OSError, pymysql.err.Error) as e:
        click.secho(str(e), err=True, fg='red')
        return 1
    finally:
        batch_h.close()
    return 0


def main_batch_without_progress_bar(mycli: 'MyCli', cli_args: 'CliArgs') -> int:
    if cli_args.batch is None:
        return 1
    if not sys.stdin.isatty() and cli_args.batch != '-':
        click.secho('Ignoring STDIN since --batch was also given.', err=True, fg='red')
    try:
        batch_h = click.open_file(cli_args.batch)
    except (OSError, FileNotFoundError):
        click.secho(f'Failed to open --batch file: {cli_args.batch}', err=True, fg='red')
        return 1
    try:
        for statement, counter in statements_from_filehandle(batch_h):
            dispatch_batch_statements(mycli, cli_args, statement, counter)
    except (ValueError, StopIteration, IOError, OSError, pymysql.err.Error) as e:
        click.secho(str(e), err=True, fg='red')
        return 1
    finally:
        batch_h.close()
    return 0


def main_batch_from_stdin(mycli: 'MyCli', cli_args: 'CliArgs') -> int:
    batch_h = click.get_text_stream('stdin')
    try:
        for statement, counter in statements_from_filehandle(batch_h):
            dispatch_batch_statements(mycli, cli_args, statement, counter)
    except (ValueError, StopIteration, IOError, OSError, pymysql.err.Error) as e:
        click.secho(str(e), err=True, fg='red')
        return 1
    return 0
