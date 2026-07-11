from __future__ import annotations

import os
import sys
import traceback
from typing import TYPE_CHECKING, Any, Literal
from urllib.parse import quote as urlquote

import click
import keyring
import pymysql
from pymysql.constants.CR import CR_SERVER_LOST
from pymysql.constants.ER import ACCESS_DENIED_ERROR, HANDSHAKE_ERROR

from mycli.compat import WIN
from mycli.config import str_to_bool
from mycli.constants import (
    DEFAULT_CHARSET,
    DEFAULT_HOST,
    DEFAULT_PORT,
    EMPTY_PASSWORD_FLAG_SENTINEL,
    ER_MUST_CHANGE_PASSWORD_LOGIN,
)
from mycli.packages.filepaths import guess_socket_location
from mycli.packages.special.utils import format_connection_dsn
from mycli.sqlexecute import SQLExecute
from mycli.ssh_tunnel import SshTunnel, SshTunnelError

try:
    from pwd import getpwuid
except ImportError:
    pass


class ClientConnectionMixin:
    if TYPE_CHECKING:
        mylogin_cnf: Any
        config: Any
        config_without_package_defaults: Any
        keepalive_ticks: int | None
        sandbox_mode: bool
        sqlexecute: Any
        logger: Any

        def read_mylogin_cnf(self, cnf: Any) -> dict[str, Any]: ...
        def echo(self, *args: Any, **kwargs: Any) -> None: ...

    def connect(
        self,
        database: str | None = "",
        user: str | None = "",
        passwd: str | int | None = None,
        host: str | None = "",
        port: str | int | None = "",
        socket: str | None = "",
        character_set: str | None = "",
        local_infile: bool | None = False,
        ssl: dict[str, Any] | None = None,
        init_command: str | None = "",
        unbuffered: bool | None = None,
        use_keyring: bool | None = None,
        reset_keyring: bool | None = None,
        keepalive_ticks: int | None = None,
        ssh_jump: str | None = None,
        ssh_cli_options: str | None = None,
    ) -> None:
        mylogin_cnf: dict[str, Any] = self.read_mylogin_cnf(self.mylogin_cnf)
        # Fall back to .mylogin.cnf values only if user did not specify a value.
        user = user or mylogin_cnf["user"] or os.getenv("USER")
        host = host or mylogin_cnf["host"]
        port = port or mylogin_cnf["port"]
        ssl_config: dict[str, Any] = ssl or {}
        user_connection_config = self.config_without_package_defaults.get('connection', {})
        self.keepalive_ticks = keepalive_ticks
        self.ssh_tunnel = None

        int_port = port and int(port)
        if not int_port:
            int_port = DEFAULT_PORT
            if not host or host == DEFAULT_HOST:
                socket = socket or user_connection_config.get("default_socket") or mylogin_cnf["socket"] or guess_socket_location()

        if ssh_jump:
            remote_host = host or DEFAULT_HOST
            remote_port = int_port or DEFAULT_PORT
            remote_socket = socket or None
            ssh_executable = self.config.get('ssh', {}).get('ssh_executable', 'ssh') or 'ssh'
            ssh_config_options = self.config.get('ssh', {}).get('ssh_options')
            tunnel_method: Literal['auto', 'socket', 'port'] = self.config.get('ssh', {}).get('tunnel_method', 'auto').lower() or 'auto'
            try:
                self.ssh_tunnel = SshTunnel.from_target(
                    ssh_jump,
                    remote_host=remote_host,
                    remote_port=int(remote_port),
                    remote_socket=remote_socket,
                    ssh_executable=ssh_executable,
                    ssh_config_options=ssh_config_options,
                    ssh_cli_options=ssh_cli_options,
                    tunnel_method=tunnel_method,
                )
                self.ssh_tunnel.start()
            except (OSError, ValueError, SshTunnelError) as exc:
                click.secho(f'Error: Unable to start SSH tunnel: {exc}', err=True, fg='red')
                try:
                    if self.ssh_tunnel:
                        self.ssh_tunnel.close()
                except Exception:
                    pass
                sys.exit(1)

        passwd = passwd if isinstance(passwd, (str, int)) else mylogin_cnf["password"]

        if not character_set:
            if 'main' in self.config_without_package_defaults and 'default_character_set' in self.config_without_package_defaults['main']:
                # migration with notice added with mycli 2.0.0 in 2026-07
                # todo: entirely remove support for default_character_set in [main]
                click.secho(
                    'Mycli 2.0 migration: automatically moving default_character_set from [main] to [connection] in ~/.myclirc .',
                    err=True,
                    fg='red',
                )
                character_set = self.config_without_package_defaults['main']['default_character_set']

                self.config_without_package_defaults.encoding = 'utf-8'
                if 'connection' not in self.config_without_package_defaults:
                    self.config_without_package_defaults['connection'] = {}
                if self.config_without_package_defaults['connection'].get('default_character_set', None) in (None, ''):
                    self.config_without_package_defaults['connection']['default_character_set'] = character_set
                else:
                    character_set = self.config_without_package_defaults["connection"].get("default_character_set")
                    click.secho(
                        f'But connection.default_character_set already existed, with the value: "{character_set}".',
                        err=True,
                        fg='red',
                    )
                del self.config_without_package_defaults['main']['default_character_set']
                self.config_without_package_defaults.write()

            if not character_set and 'default_character_set' in self.config['connection']:
                character_set = self.config['connection']['default_character_set']
        if not character_set:
            character_set = DEFAULT_CHARSET

        # Favor whichever local_infile option is set.
        use_local_infile = False
        for local_infile_option in (
            local_infile,
            user_connection_config.get('default_local_infile'),
            False,
        ):
            try:
                use_local_infile = str_to_bool(local_infile_option or '')
                break
            except (TypeError, ValueError):
                pass

        if 'default_ssl_ca_path' in self.config['connection'] and (not ssl_config or not ssl_config.get('capath')):
            ssl_config['capath'] = self.config['connection']['default_ssl_ca_path'] or False

        # prune lone check_hostname=False
        if not any(v for v in ssl_config.values()):
            ssl_config = {}

        # password hierarchy
        # 1. -p / --pass/--password CLI options
        # 2. --password-file CLI option
        # 3. envvar (MYSQL_PWD)
        # 4. DSN (mysql://user:password)
        # 5. .mylogin.cnf
        # 6. keyring

        ssh_tunnel_field = urlquote(ssh_jump or '')
        if ssh_tunnel_field:
            ssh_tunnel_field = ':' + ssh_tunnel_field
        keyring_identifier = f'{user}@{host}:{"" if socket else int_port}:{socket or ""}{ssh_tunnel_field}'
        keyring_domain = 'mycli.net'
        keyring_retrieved_cleanly = False

        if passwd is None and use_keyring and not reset_keyring:
            passwd = keyring.get_password(keyring_domain, keyring_identifier)
            if passwd is not None:
                keyring_retrieved_cleanly = True

        # prompt for password if requested by user
        if passwd == EMPTY_PASSWORD_FLAG_SENTINEL:
            passwd = click.prompt(f"Enter password for {user}", hide_input=True, show_default=False, default='', type=str, err=True)
            keyring_retrieved_cleanly = False

        # should not fail, but will help the typechecker
        assert not isinstance(passwd, int)

        display_dsn = None
        if self.ssh_tunnel:
            display_dsn = format_connection_dsn(
                user=user,
                host=remote_host,
                port=remote_port,
                socket=remote_socket,
                database=database,
                character_set=character_set,
                ssh_jump=ssh_jump,
            )

        connection_info: dict[str, Any] = {
            'database': database,
            'user': user,
            'password': passwd,
            'character_set': character_set,
            'local_infile': use_local_infile,
            'ssl': ssl_config,
            'init_command': init_command,
            'unbuffered': unbuffered,
            'display_dsn': display_dsn,
        }
        if self.ssh_tunnel and self.ssh_tunnel.local_socket:
            connection_info['host'] = None
            connection_info['port'] = None
            connection_info['socket'] = self.ssh_tunnel.local_socket
        elif self.ssh_tunnel:
            connection_info['host'] = self.ssh_tunnel.local_host
            connection_info['port'] = self.ssh_tunnel.local_port
            connection_info['socket'] = None
        else:
            connection_info['host'] = host
            connection_info['port'] = int_port
            connection_info['socket'] = socket

        def _update_keyring(password: str | None, keyring_retrieved_cleanly: bool):
            if not password:
                return
            if reset_keyring or (use_keyring and not keyring_retrieved_cleanly):
                try:
                    saved_pw = keyring.get_password(keyring_domain, keyring_identifier)
                    if password != saved_pw or reset_keyring:
                        keyring.set_password(keyring_domain, keyring_identifier, password)
                        click.secho(f'Password saved to the system keyring at {keyring_domain}/{keyring_identifier}', err=True)
                except Exception as e:
                    click.secho(f'Password not saved to the system keyring: {e}', err=True, fg='red')

        def _connect(
            retry_ssl: bool = False,
            retry_password: bool = False,
            keyring_save_eligible: bool = True,
            keyring_retrieved_cleanly: bool = False,
        ) -> None:
            try:
                if keyring_save_eligible:
                    _update_keyring(connection_info["password"], keyring_retrieved_cleanly=keyring_retrieved_cleanly)
                self.sqlexecute = SQLExecute(**connection_info)
            except pymysql.OperationalError as e1:
                if e1.args[0] == HANDSHAKE_ERROR and ssl is not None and ssl.get("mode", None) == "auto":
                    # if we already tried and failed to connect without SSL, raise the error
                    if retry_ssl:
                        raise e1
                    # disable SSL and try to connect again
                    connection_info["ssl"] = None
                    _connect(
                        retry_ssl=True, keyring_retrieved_cleanly=keyring_retrieved_cleanly, keyring_save_eligible=keyring_save_eligible
                    )
                elif e1.args[0] == ACCESS_DENIED_ERROR and connection_info["password"] is None:
                    # if we already tried and failed to connect with a new password, raise the error
                    if retry_password:
                        raise e1
                    # ask the user for a new password and try to connect again
                    new_password = click.prompt(
                        f"Enter password for {user}", hide_input=True, show_default=False, default='', type=str, err=True
                    )
                    connection_info["password"] = new_password
                    keyring_retrieved_cleanly = False
                    _connect(
                        retry_password=True,
                        keyring_retrieved_cleanly=keyring_retrieved_cleanly,
                        keyring_save_eligible=keyring_save_eligible,
                    )
                elif e1.args[0] == ER_MUST_CHANGE_PASSWORD_LOGIN:
                    self.echo(
                        "Your password has expired and the server rejected the connection.",
                        err=True,
                        fg='red',
                    )
                    raise e1
                elif e1.args[0] == CR_SERVER_LOST:
                    self.echo(
                        (
                            "Connection to server lost. If this error persists, it may be a mismatch between the server and "
                            "client SSL configuration. To troubleshoot the issue, try --ssl-mode=off or --ssl-mode=on."
                        ),
                        err=True,
                        fg='red',
                    )
                    raise e1
                else:
                    raise e1

        try:
            if not WIN and socket:
                try:
                    socket_owner = getpwuid(os.stat(socket).st_uid).pw_name
                except KeyError:
                    socket_owner = '<unknown>'
                except FileNotFoundError:
                    socket_owner = '<unknown>'
                self.echo(f"Connecting to socket {socket}, owned by user {socket_owner}", err=True)
                try:
                    _connect(keyring_retrieved_cleanly=keyring_retrieved_cleanly)
                except pymysql.OperationalError as e:
                    # These are "Can't open socket" and 2x "Can't connect"
                    if [code for code in (2001, 2002, 2003) if code == e.args[0]]:
                        self.logger.debug("Database connection failed: %r.", e)
                        self.logger.error("traceback: %r", traceback.format_exc())
                        self.logger.debug("Retrying over TCP/IP")
                        self.echo(f"Failed to connect to local MySQL server through socket '{socket}':")
                        self.echo(str(e), err=True)
                        self.echo("Retrying over TCP/IP", err=True)

                        # Else fall back to TCP/IP localhost
                        socket = ""
                        host = DEFAULT_HOST
                        port = DEFAULT_PORT
                        # todo should reload the keyring identifier here instead of invalidating
                        _connect(keyring_save_eligible=False)
                    else:
                        raise e
            else:
                host = host or DEFAULT_HOST
                port = port or DEFAULT_PORT
                # could try loading the keyring again here instead of assuming nothing important changed

                # Bad ports give particularly daft error messages
                try:
                    port = int(port)
                except ValueError:
                    self.echo(f"Error: Invalid port number: '{port}'.", err=True, fg="red")
                    sys.exit(1)

                _connect(keyring_retrieved_cleanly=keyring_retrieved_cleanly)

            # Check if SQLExecute detected sandbox mode during connection
            if self.sqlexecute and self.sqlexecute.sandbox_mode:
                self.sandbox_mode = True
                self.echo(
                    "Your password has expired. Use ALTER USER or SET PASSWSORD to set a new password, or quit.",
                    err=True,
                    fg='yellow',
                )
        except Exception as e:  # Connecting to a database could fail.
            self.logger.debug("Database connection failed: %r.", e)
            self.logger.error("traceback: %r", traceback.format_exc())
            self.echo(str(e), err=True, fg="red")
            sys.exit(1)

    def reconnect(self, database: str = "") -> bool:
        """
        Attempt to reconnect to the server. Return True if successful,
        False if unsuccessful.

        The "database" argument is used only to improve messages.
        """
        assert self.sqlexecute is not None
        assert self.sqlexecute.conn is not None

        # First pass with ping(reconnect=False) and minimal feedback levels.  This definitely
        # works as expected, and is a good idea especially when "connect" was used as a
        # synonym for "use".
        try:
            self.sqlexecute.conn.ping(reconnect=False)
            if not database:
                self.echo("Already connected.", fg="yellow")
            return True
        except pymysql.err.Error:
            pass

        # Second pass with ping(reconnect=True).  It is not demonstrated that this pass ever
        # gives the benefit it is looking for, _ie_ preserves session state.  We need to test
        # this with connection pooling.
        try:
            old_connection_id = self.sqlexecute.connection_id
            self.logger.debug("Attempting to reconnect.")
            self.echo("Reconnecting...", fg="yellow")
            self.sqlexecute.conn.ping(reconnect=True)
            # if a database is currently selected, set it on the conn again
            if self.sqlexecute.dbname:
                self.sqlexecute.conn.select_db(self.sqlexecute.dbname)
            self.logger.debug("Reconnected successfully.")
            self.echo("Reconnected successfully.", fg="yellow")
            self.sqlexecute.reset_connection_id()
            if old_connection_id != self.sqlexecute.connection_id:
                self.echo("Any session state was reset.", fg="red")
            return True
        except pymysql.err.Error:
            pass

        # Third pass with sqlexecute.connect() should always work, but always resets session state.
        try:
            self.logger.debug("Creating new connection")
            self.echo("Creating new connection...", fg="yellow")
            self.sqlexecute.connect()
            self.logger.debug("New connection created successfully.")
            self.echo("New connection created successfully.", fg="yellow")
            self.echo("Any session state was reset.", fg="red")
            return True
        except pymysql.OperationalError as e:
            self.logger.debug("Reconnect failed. e: %r", e)
            self.echo(str(e), err=True, fg="red")
            return False
