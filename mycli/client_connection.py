from __future__ import annotations

import os
import sys
import traceback
from typing import TYPE_CHECKING, Any

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
from mycli.sqlexecute import SQLExecute

try:
    from pwd import getpwuid
except ImportError:
    pass


class ClientConnectionMixin:
    if TYPE_CHECKING:
        my_cnf: Any
        config: Any
        config_without_package_defaults: Any
        keepalive_ticks: int | None
        sandbox_mode: bool
        sqlexecute: Any
        logger: Any

        def read_my_cnf(self, files: Any, keys: list[str]) -> dict[str, Any]: ...
        def merge_ssl_with_cnf(self, ssl_config: dict[str, Any], cnf: dict[str, Any]) -> dict[str, Any] | None: ...
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
        ssh_user: str | None = "",
        ssh_host: str | None = "",
        ssh_port: int = 22,
        ssh_password: str | None = "",
        ssh_key_filename: str | None = "",
        init_command: str | None = "",
        unbuffered: bool | None = None,
        use_keyring: bool | None = None,
        reset_keyring: bool | None = None,
        keepalive_ticks: int | None = None,
    ) -> None:
        cnf = {
            "database": None,
            "user": None,
            "password": None,
            "host": None,
            "port": None,
            "socket": None,
            "default_socket": None,
            "default-character-set": None,
            "local-infile": None,
            "loose-local-infile": None,
            "ssl-ca": None,
            "ssl-cert": None,
            "ssl-key": None,
            "ssl-cipher": None,
            "ssl-verify-server-cert": None,
        }

        cnf = self.read_my_cnf(self.my_cnf, list(cnf.keys()))

        # Fall back to config values only if user did not specify a value.
        database = database or cnf["database"]
        user = user or cnf["user"] or os.getenv("USER")
        host = host or cnf["host"]
        port = port or cnf["port"]
        ssl_config: dict[str, Any] = ssl or {}
        user_connection_config = self.config_without_package_defaults.get('connection', {})
        self.keepalive_ticks = keepalive_ticks

        int_port = port and int(port)
        if not int_port:
            int_port = DEFAULT_PORT
            if not host or host == DEFAULT_HOST:
                socket = (
                    socket
                    or user_connection_config.get("default_socket")
                    or cnf["socket"]
                    or cnf["default_socket"]
                    or guess_socket_location()
                )

        passwd = passwd if isinstance(passwd, (str, int)) else cnf["password"]

        # default_character_set doesn't check in self.config_without_package_defaults, because the
        # option already existed before the my.cnf deprecation.  For the same reason,
        # default_character_set can be in [connection] or [main].
        if not character_set:
            if 'default_character_set' in self.config['connection']:
                character_set = self.config['connection']['default_character_set']
            elif 'default_character_set' in self.config['main']:
                character_set = self.config['main']['default_character_set']
            elif 'default_character_set' in cnf:
                character_set = cnf['default_character_set']
            elif 'default-character-set' in cnf:
                character_set = cnf['default-character-set']
        if not character_set:
            character_set = DEFAULT_CHARSET

        # Favor whichever local_infile option is set.
        use_local_infile = False
        for local_infile_option in (
            local_infile,
            user_connection_config.get('default_local_infile'),
            cnf['local_infile'],
            cnf['local-infile'],
            cnf['loose_local_infile'],
            cnf['loose-local-infile'],
            False,
        ):
            try:
                use_local_infile = str_to_bool(local_infile_option or '')
                break
            except (TypeError, ValueError):
                pass

        # temporary my.cnf override mappings
        if 'default_ssl_ca' in user_connection_config:
            cnf['ssl-ca'] = user_connection_config.get('default_ssl_ca') or None
        if 'default_ssl_cert' in user_connection_config:
            cnf['ssl-cert'] = user_connection_config.get('default_ssl_cert') or None
        if 'default_ssl_key' in user_connection_config:
            cnf['ssl-key'] = user_connection_config.get('default_ssl_key') or None
        if 'default_ssl_cipher' in user_connection_config:
            cnf['ssl-cipher'] = user_connection_config.get('default_ssl_cipher') or None
        if 'default_ssl_verify_server_cert' in user_connection_config:
            cnf['ssl-verify-server-cert'] = user_connection_config.get('default_ssl_verify_server_cert') or None

        # todo: rewrite the merge method using self.config['connection'] instead of cnf, after removing my.cnf support
        ssl_config_or_none: dict[str, Any] | None = self.merge_ssl_with_cnf(ssl_config, cnf)

        # default_ssl_ca_path is not represented in my.cnf
        if 'default_ssl_ca_path' in self.config['connection'] and (not ssl_config_or_none or not ssl_config_or_none.get('capath')):
            if ssl_config_or_none is None:
                ssl_config_or_none = {}
            ssl_config_or_none['capath'] = self.config['connection']['default_ssl_ca_path'] or False

        # prune lone check_hostname=False
        if not any(v for v in ssl_config.values()):
            ssl_config_or_none = None

        # password hierarchy
        # 1. -p / --pass/--password CLI options
        # 2. --password-file CLI option
        # 3. envvar (MYSQL_PWD)
        # 4. DSN (mysql://user:password)
        # 5. cnf (.my.cnf / etc)
        # 6. keyring

        keyring_identifier = f'{user}@{host}:{"" if socket else int_port}:{socket or ""}'
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

        connection_info: dict[Any, Any] = {
            "database": database,
            "user": user,
            "password": passwd,
            "host": host,
            "port": int_port,
            "socket": socket,
            "character_set": character_set,
            "local_infile": use_local_infile,
            "ssl": ssl_config_or_none,
            "ssh_user": ssh_user,
            "ssh_host": ssh_host,
            "ssh_port": int(ssh_port) if ssh_port else None,
            "ssh_password": ssh_password,
            "ssh_key_filename": ssh_key_filename,
            "init_command": init_command,
            "unbuffered": unbuffered,
        }

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
