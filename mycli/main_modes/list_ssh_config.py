from __future__ import annotations

from typing import TYPE_CHECKING

import click

from mycli.packages.ssh_utils import read_ssh_config

if TYPE_CHECKING:
    from mycli.main import CliArgs, MyCli


def main_list_ssh_config(mycli: 'MyCli', cli_args: 'CliArgs') -> int:
    ssh_config = read_ssh_config(cli_args.ssh_config_path)
    try:
        host_entries = ssh_config.get_hostnames()
    except KeyError:
        click.secho('Error reading ssh config', err=True, fg="red")
        return 1
    for host_entry in host_entries:
        if mycli.verbosity >= 1:
            host_config = ssh_config.lookup(host_entry)
            click.secho(f"{host_entry} : {host_config.get('hostname')}")
        else:
            click.secho(host_entry)
    return 0
