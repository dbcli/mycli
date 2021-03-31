"""A very thin wrapper around paramiko, mostly to keep all SSH-related
functionality in one place."""
from io import open
import logging

_logger = logging.getLogger(__name__)

try:
    import paramiko
except ImportError:
    from mycli.packages.paramiko_stub import paramiko


class SSHException(Exception):
    pass


def get_config_hosts(config_path):
    config = read_config_file(config_path)
    return {
        host: config.lookup(host).get("hostname") for host in config.get_hostnames()
    }


def create_ssh_client(ssh_host, ssh_port, ssh_user, ssh_password=None, ssh_key_filename=None) -> paramiko.SSHClient:
    client = paramiko.SSHClient()
    client.load_system_host_keys()
    client.set_missing_host_key_policy(paramiko.WarningPolicy())
    _logger.debug(
        f'Connecting to ssh server with \n'
        '  host = {ssh_host}\n'
        '  port = {ssh_port}\n'
        '  user = {ssh_user}\n'
        '  password = {ssh_password}\n'
        '  key_filename = {ssh_key_filename}\n'
    )
    client.connect(
        ssh_host, ssh_port, ssh_user, password=ssh_password, key_filename=ssh_key_filename
    )
    return client


def read_config_file(config_path) -> paramiko.SSHConfig:
    ssh_config = paramiko.config.SSHConfig()
    try:
        with open(config_path) as f:
            ssh_config.parse(f)
    except FileNotFoundError as e:
        raise SSHException(str(e))
    # Paramiko prior to version 2.7 raises Exception on parse errors.
    # In 2.7 it has become paramiko.ssh_exception.SSHException,
    # but let's catch everything for compatibility
    except Exception as err:
        raise SSHException(
            f"Could not parse SSH configuration file {config_path}:\n{err} ",
        )
    return ssh_config
