import sys

import click

try:
    import paramiko
except ImportError:
    from mycli.packages.paramiko_stub import paramiko  # type: ignore[no-redef]


# it isn't cool that this utility function can exit(), but it is slated to be removed anyway
def read_ssh_config(ssh_config_path: str):
    ssh_config = paramiko.config.SSHConfig()
    try:
        with open(ssh_config_path) as f:
            ssh_config.parse(f)
    except FileNotFoundError as e:
        click.secho(str(e), err=True, fg="red")
        sys.exit(1)
    # Paramiko prior to version 2.7 raises Exception on parse errors.
    # In 2.7 it has become paramiko.ssh_exception.SSHException,
    # but let's catch everything for compatibility
    except Exception as err:
        click.secho(f"Could not parse SSH configuration file {ssh_config_path}:\n{err} ", err=True, fg="red")
        sys.exit(1)
    else:
        return ssh_config
