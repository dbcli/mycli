from __future__ import annotations

import os
import re
import sys
from typing import TYPE_CHECKING, Any, Callable
from urllib.parse import parse_qs, unquote, urlparse

import click

from mycli.config import str_to_bool
from mycli.constants import EMPTY_PASSWORD_FLAG_SENTINEL
from mycli.main_modes.batch import main_batch_from_stdin, main_batch_with_progress_bar, main_batch_without_progress_bar
from mycli.main_modes.checkup import main_checkup
from mycli.main_modes.execute import main_execute_from_cli
from mycli.main_modes.list_dsn import main_list_dsn
from mycli.packages.cli_utils import is_valid_connection_scheme
from mycli.password_sources import PasswordCandidates
from mycli.vault import (
    DEFAULT_VAULT_EXECUTABLE,
    DEFAULT_VAULT_PASSWORD_FIELD,
    DEFAULT_VAULT_USERNAME_FIELD,
    VaultError,
    get_field_from_vault,
)

if TYPE_CHECKING:
    from mycli.main import CliArgs

ClientFactory = Callable[..., Any]
ENV_VAR_PATTERN = re.compile(r'^\$\{([A-Za-z_][A-Za-z0-9_]*)\}$')
KNOWN_DSN_QUERY_PARAMS = {
    'character_set',
    'keepalive_ticks',
    'socket',
    'ssh_jump',
    'ssl_ca',
    'ssl_capath',
    'ssl_cert',
    'ssl_cipher',
    'ssl_key',
    'ssl_mode',
    'ssl_verify_server_cert',
    'tls_version',
    'vault_address',
    'vault_mount',
    'vault_secret',
    'vault_password_field',
    'vault_username_field',
}


class DsnAliasEnvVarError(ValueError):
    pass


def expand_dsn_alias_env_var(value: str | None, alias_name: str) -> str | None:
    if value is None:
        return None

    match = ENV_VAR_PATTERN.fullmatch(value)
    if not match:
        return value

    var_name = match.group(1)
    try:
        return os.environ[var_name]
    except KeyError as exc:
        raise DsnAliasEnvVarError(f'Environment variable {var_name} referenced by DSN alias {alias_name} is not set.') from exc


def split_dsn_netloc(netloc: str) -> tuple[str | None, str | None, str | None, str | None]:
    username = None
    password = None
    host_port = netloc

    if '@' in host_port:
        user_info, host_port = host_port.rsplit('@', 1)
        username, separator, password = user_info.partition(':')
        if not separator:
            password = None

    if not host_port:
        return username, password, None, None

    if host_port.startswith('['):
        end = host_port.find(']')
        if end >= 0:
            host = host_port[1:end]
            port = host_port[end + 2 :] if host_port[end + 1 : end + 2] == ':' else None
            return username, password, host, port

    host, separator, port = host_port.partition(':')
    return username, password, host or None, port if separator else None


def expand_dsn_alias_env_vars(
    dsn_uri: str, alias_name: str
) -> tuple[str | None, str | None, str | None, int | None, str, dict[str, list[str]]]:
    uri = urlparse(dsn_uri)
    username, password, host, port = split_dsn_netloc(uri.netloc)

    expanded_port = expand_dsn_alias_env_var(port, alias_name)
    try:
        port_number = int(expanded_port) if expanded_port else None
    except ValueError as exc:
        raise DsnAliasEnvVarError(f'Port in DSN alias {alias_name} must be an integer.') from exc

    params = {
        key: [expand_dsn_alias_env_var(value, alias_name) or '' for value in values]
        for key, values in parse_qs(uri.query, keep_blank_values=True).items()
    }

    return (
        expand_dsn_alias_env_var(unquote(username) if username is not None else None, alias_name),
        expand_dsn_alias_env_var(unquote(password) if password is not None else None, alias_name),
        expand_dsn_alias_env_var(host, alias_name),
        port_number,
        expand_dsn_alias_env_var(uri.path[1:], alias_name) or '',
        params,
    )


def run_from_cli_args(cli_args: 'CliArgs', client_factory: ClientFactory) -> None:
    from mycli import main as main_module

    cli_verbosity = main_module.preprocess_cli_args(cli_args, is_valid_connection_scheme)

    mycli = client_factory(
        prompt=cli_args.prompt,
        toolbar_format=cli_args.toolbar,
        logfile=cli_args.logfile,
        login_path=cli_args.login_path,
        auto_vertical_output=cli_args.auto_vertical_output,
        warn=cli_args.warn,
        myclirc=cli_args.myclirc,
        show_warnings=cli_args.show_warnings,
        cli_verbosity=cli_verbosity,
    )

    if cli_args.checkup:
        main_checkup(mycli)
        sys.exit(0)

    if cli_args.csv and cli_args.format not in [None, 'csv']:
        click.secho("Conflicting --csv and --format arguments.", err=True, fg="red")
        sys.exit(1)

    if cli_args.table and cli_args.format not in [None, 'table']:
        click.secho("Conflicting --table and --format arguments.", err=True, fg="red")
        sys.exit(1)

    if not cli_args.format:
        cli_args.format = 'default'

    if cli_args.csv:
        cli_args.format = 'csv'

    if cli_args.table:
        cli_args.format = 'table'

    if cli_args.list_dsn:
        sys.exit(main_list_dsn(mycli))

    # Choose which ever one has a valid value.
    database = cli_args.dbname or cli_args.database

    dsn_uri = None
    dsn_password: str | None = None

    # Treat the database argument as a DSN alias only if it matches a configured alias
    # todo why is port tested but not socket?
    truthy_password = (
        cli_args.password not in (None, EMPTY_PASSWORD_FLAG_SENTINEL)
        or cli_args.password_file is not None
        or os.environ.get('MYSQL_PWD') is not None
    )
    if (
        database
        and "://" not in database
        and not any([
            cli_args.user,
            truthy_password,
            cli_args.host,
            cli_args.port,
            cli_args.login_path,
        ])
        and database in mycli.config.get("alias_dsn", {})
    ):
        cli_args.dsn, database = database, ""

    if database and "://" in database:
        dsn_uri, database = database, ""

    if cli_args.dsn:
        try:
            dsn_uri = mycli.config["alias_dsn"][cli_args.dsn]
        except KeyError:
            is_valid_scheme, scheme = is_valid_connection_scheme(cli_args.dsn)
            if is_valid_scheme:
                dsn_uri = cli_args.dsn
            else:
                click.secho(
                    "Could not find the specified DSN in the config file. Please check the \"[alias_dsn]\" section in your myclirc.",
                    err=True,
                    fg="red",
                )
                sys.exit(1)
        else:
            mycli.dsn_alias = cli_args.dsn

    if dsn_uri:
        is_valid_scheme, scheme = is_valid_connection_scheme(dsn_uri)
        if not is_valid_scheme:
            click.secho(f'Error: Unknown connection scheme provided for DSN URI ({scheme}://)', err=True, fg='red')
            sys.exit(1)

        uri = urlparse(dsn_uri)
        env_var_alias_name = None
        dsn_alias = getattr(mycli, 'dsn_alias', None)
        if dsn_alias and str_to_bool(mycli.config['main'].get('expand_dsn_alias_env_vars', 'False')):
            env_var_alias_name = dsn_alias

        if env_var_alias_name:
            try:
                dsn_user, dsn_password, dsn_host, dsn_port, dsn_database, dsn_params = expand_dsn_alias_env_vars(
                    dsn_uri, env_var_alias_name
                )
            except DsnAliasEnvVarError as exc:
                click.secho(str(exc), err=True, fg='red')
                sys.exit(1)
        else:
            dsn_user = unquote(uri.username) if uri.username is not None else None
            dsn_password = unquote(uri.password) if uri.password is not None else None
            dsn_host = uri.hostname
            dsn_port = uri.port
            dsn_database = uri.path[1:]
            dsn_params = parse_qs(uri.query, keep_blank_values=True) if uri.query else {}

        if not database:
            database = dsn_database
        if not cli_args.user and dsn_user is not None:
            cli_args.user = dsn_user
        if not cli_args.host:
            cli_args.host = dsn_host
        if not cli_args.port:
            cli_args.port = dsn_port

        if unknown_dsn_params := sorted(set(dsn_params) - KNOWN_DSN_QUERY_PARAMS):
            click.secho(
                f'Warning: Ignored unknown DSN URI query parameters: {", ".join(unknown_dsn_params)}.',
                err=True,
                fg='yellow',
            )

        if params := dsn_params.get('ssl_mode'):
            cli_args.ssl_mode = cli_args.ssl_mode or params[0]
        if params := dsn_params.get('ssl_ca'):
            cli_args.ssl_ca = cli_args.ssl_ca or params[0]
            cli_args.ssl_mode = cli_args.ssl_mode or 'on'
        if params := dsn_params.get('ssl_capath'):
            cli_args.ssl_capath = cli_args.ssl_capath or params[0]
            cli_args.ssl_mode = cli_args.ssl_mode or 'on'
        if params := dsn_params.get('ssl_cert'):
            cli_args.ssl_cert = cli_args.ssl_cert or params[0]
            cli_args.ssl_mode = cli_args.ssl_mode or 'on'
        if params := dsn_params.get('ssl_key'):
            cli_args.ssl_key = cli_args.ssl_key or params[0]
            cli_args.ssl_mode = cli_args.ssl_mode or 'on'
        if params := dsn_params.get('ssl_cipher'):
            cli_args.ssl_cipher = cli_args.ssl_cipher or params[0]
            cli_args.ssl_mode = cli_args.ssl_mode or 'on'
        if params := dsn_params.get('tls_version'):
            cli_args.tls_version = cli_args.tls_version or params[0]
            cli_args.ssl_mode = cli_args.ssl_mode or 'on'
        if params := dsn_params.get('ssl_verify_server_cert'):
            cli_args.ssl_verify_server_cert = cli_args.ssl_verify_server_cert or (params[0].lower() == 'true')
            cli_args.ssl_mode = cli_args.ssl_mode or 'on'
        if params := dsn_params.get('socket'):
            cli_args.socket = cli_args.socket or params[0]
        if params := dsn_params.get('keepalive_ticks'):
            if cli_args.keepalive_ticks is None:
                cli_args.keepalive_ticks = int(params[0])
        if params := dsn_params.get('character_set'):
            cli_args.character_set = cli_args.character_set or params[0]
        if params := dsn_params.get('ssh_jump'):
            cli_args.ssh_jump = cli_args.ssh_jump or params[0]
        if params := dsn_params.get('vault_address'):
            cli_args.vault_address = cli_args.vault_address or params[0]
        if params := dsn_params.get('vault_mount'):
            cli_args.vault_mount = cli_args.vault_mount or params[0]
        if params := dsn_params.get('vault_secret'):
            cli_args.vault_secret = cli_args.vault_secret or params[0]
        if params := dsn_params.get('vault_password_field'):
            cli_args.vault_password_field = cli_args.vault_password_field or params[0]
        if params := dsn_params.get('vault_username_field'):
            cli_args.vault_username_field = cli_args.vault_username_field or params[0]

    keepalive_ticks = cli_args.keepalive_ticks if cli_args.keepalive_ticks is not None else mycli.default_keepalive_ticks
    ssl_mode = cli_args.ssl_mode or mycli.ssl_mode

    if ssl_mode in ("auto", "on"):
        if cli_args.socket and ssl_mode == 'auto':
            ssl = None
        else:
            ssl = {
                "mode": ssl_mode,
                "ca": cli_args.ssl_ca and os.path.expanduser(cli_args.ssl_ca),
                "cert": cli_args.ssl_cert and os.path.expanduser(cli_args.ssl_cert),
                "key": cli_args.ssl_key and os.path.expanduser(cli_args.ssl_key),
                "capath": cli_args.ssl_capath,
                "cipher": cli_args.ssl_cipher,
                "tls_version": cli_args.tls_version,
                "check_hostname": cli_args.ssl_verify_server_cert,
            }
            # remove empty ssl options
            ssl = {k: v for k, v in ssl.items() if v is not None}
    else:
        ssl = None

    # Merge init-commands: global, DSN-specific, then CLI
    init_cmds: list[str] = []
    # 1) Global init-commands
    global_section = mycli.config.get("init-commands", {})
    for _, val in global_section.items():
        if isinstance(val, (list, tuple)):
            init_cmds.extend(val)
        elif val:
            init_cmds.append(val)
    # 2) DSN-specific init-commands
    if cli_args.dsn:
        alias_section = mycli.config.get("alias_dsn.init-commands", {})
        if cli_args.dsn in alias_section:
            val = alias_section.get(cli_args.dsn)
            if isinstance(val, (list, tuple)):
                init_cmds.extend(val)
            elif val:
                init_cmds.append(val)
    # 3) CLI-provided init_command
    if cli_args.init_command:
        init_cmds.append(cli_args.init_command)

    combined_init_cmd = "; ".join(cmd.strip() for cmd in init_cmds if cmd)

    if cli_args.use_keyring is not None and cli_args.use_keyring.lower() == 'reset':
        use_keyring = True
        reset_keyring = True
    elif cli_args.use_keyring is not None and cli_args.use_keyring.lower() == 'auto':
        if os.environ.get('SSH_CONNECTION'):
            use_keyring = False
            reset_keyring = False
        else:
            use_keyring = True
            reset_keyring = False
    elif cli_args.use_keyring is None:
        if mycli.config['main'].get('use_keyring', 'False').lower() == 'auto':
            if os.environ.get('SSH_CONNECTION'):
                use_keyring = False
                reset_keyring = False
            else:
                use_keyring = True
                reset_keyring = False
        else:
            use_keyring = str_to_bool(mycli.config['main'].get('use_keyring', 'False'))
            reset_keyring = False
    else:
        use_keyring = str_to_bool(cli_args.use_keyring)
        reset_keyring = False

    password_candidates = PasswordCandidates()
    if cli_args.password == EMPTY_PASSWORD_FLAG_SENTINEL:
        password_candidates.add_value('prompt', cli_args.password)
    elif cli_args.password is not None:
        password_candidates.add_value('cli_literal', cli_args.password)
    if cli_args.password_file:
        password_candidates.add_loader('cli_file', lambda: main_module.get_password_from_file(cli_args.password_file))
    if os.environ.get('MYSQL_PWD') is not None:
        password_candidates.add_value('environment', os.environ.get('MYSQL_PWD'))
    if dsn_password is not None:
        password_candidates.add_value('dsn', dsn_password)

    if cli_args.vault_secret:
        vault_secret = cli_args.vault_secret
        vault_config = mycli.config.get('vault_beta', {})
        vault_address = cli_args.vault_address or os.environ.get('VAULT_ADDR') or vault_config.get('address') or None
        vault_mount = cli_args.vault_mount or vault_config.get('default_mount') or None
        vault_field = cli_args.vault_password_field or vault_config.get('default_password_field') or DEFAULT_VAULT_PASSWORD_FIELD
        vault_executable = vault_config.get('vault_executable') or DEFAULT_VAULT_EXECUTABLE

        def load_vault_password() -> str | None:
            try:
                return get_field_from_vault(
                    vault_field,
                    vault_secret,
                    executable=vault_executable,
                    mount=vault_mount,
                    address=vault_address,
                )
            except VaultError as exc:
                click.secho(f'Error reading password from Vault: {exc}', err=True, fg='red')
                sys.exit(1)

        password_candidates.add_loader('vault', load_vault_password)

    if cli_args.user is None and cli_args.vault_secret:
        vault_config = mycli.config.get('vault_beta', {})
        vault_address = cli_args.vault_address or os.environ.get('VAULT_ADDR') or vault_config.get('address') or None
        vault_mount = cli_args.vault_mount or vault_config.get('default_mount') or None
        vault_field = cli_args.vault_username_field or vault_config.get('default_username_field') or DEFAULT_VAULT_USERNAME_FIELD
        vault_executable = vault_config.get('vault_executable') or DEFAULT_VAULT_EXECUTABLE
        try:
            vault_username = get_field_from_vault(
                vault_field,
                cli_args.vault_secret,
                executable=vault_executable,
                mount=vault_mount,
                address=vault_address,
            )
        except VaultError as exc:
            click.secho(f'Error reading username from Vault: {exc}', err=True, fg='red')
            sys.exit(1)
    else:
        vault_username = None
    vault_username_from_vault = vault_username is not None

    try:
        mycli.connect(
            database=database,
            user=vault_username if cli_args.user is None else cli_args.user,
            password_candidates=password_candidates,
            host=cli_args.host,
            port=cli_args.port,
            socket=cli_args.socket,
            local_infile=cli_args.local_infile,
            ssl=ssl,
            init_command=combined_init_cmd,
            unbuffered=cli_args.unbuffered,
            character_set=cli_args.character_set,
            use_keyring=use_keyring,
            reset_keyring=reset_keyring,
            keepalive_ticks=keepalive_ticks,
            ssh_jump=cli_args.ssh_jump,
            ssh_cli_options=cli_args.ssh_options,
            vault_address=cli_args.vault_address,
            vault_mount=cli_args.vault_mount,
            vault_secret=cli_args.vault_secret,
            vault_password_field=cli_args.vault_password_field,
            vault_username_field=cli_args.vault_username_field,
            vault_username_from_vault=vault_username_from_vault,
        )

        if combined_init_cmd:
            click.echo(f"Executing init-command: {combined_init_cmd}", err=True)

        mycli.logger.debug(
            "Launch Params: \n\tdatabase: %r\tuser: %r\thost: %r\tport: %r",
            database,
            cli_args.user,
            cli_args.host,
            cli_args.port,
        )

        if cli_args.execute is not None:
            sys.exit(main_execute_from_cli(mycli, cli_args))

        if cli_args.batch is not None and cli_args.batch != '-' and cli_args.progress and sys.stderr.isatty():
            sys.exit(main_batch_with_progress_bar(mycli, cli_args))

        if cli_args.batch is not None:
            sys.exit(main_batch_without_progress_bar(mycli, cli_args))

        if not sys.stdin.isatty():
            sys.exit(main_batch_from_stdin(mycli, cli_args))

        mycli.run_cli()
    finally:
        mycli.close()
