from __future__ import annotations

from typing import TYPE_CHECKING

import click

if TYPE_CHECKING:
    from mycli.main import CliArgs, MyCli


def main_list_dsn(mycli: 'MyCli', cli_args: 'CliArgs') -> int:
    try:
        alias_dsn = mycli.config['alias_dsn']
    except KeyError:
        click.secho('Invalid DSNs found in the config file. Please check the "[alias_dsn]" section in myclirc.', err=True, fg='red')
        return 1
    except Exception as e:
        click.secho(str(e), err=True, fg='red')
        return 1
    for alias, value in alias_dsn.items():
        if cli_args.verbose:
            click.secho(f'{alias} : {value}')
        else:
            click.secho(alias)
    return 0
