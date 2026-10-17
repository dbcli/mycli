from __future__ import annotations

import click
from configobj import ConfigObj

from mycli.config import read_user_config
from mycli.packages.utils.dsn_utils import is_valid_dsn_alias, merge_shared_dsns


def load_list_dsn_config(myclirc: str | None) -> ConfigObj:
    config = read_user_config(myclirc)
    merge_shared_dsns(config, config['main'].get('shared_dsns_file'))
    return config


def main_list_dsn(config: ConfigObj, verbosity: int) -> int:
    try:
        alias_dsn = config['alias_dsn']
    except KeyError:
        click.secho('Invalid DSNs found in the config file. Please check the "[alias_dsn]" section in myclirc.', err=True, fg='red')
        return 1
    except Exception as e:
        click.secho(str(e), err=True, fg='red')
        return 1
    for alias, value in alias_dsn.items():
        if not is_valid_dsn_alias(alias):
            continue
        if verbosity >= 1:
            click.secho(f'{alias} : {value}')
        else:
            click.secho(alias)
    return 0
