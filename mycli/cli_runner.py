from __future__ import annotations

import os
import re
import sys
from textwrap import dedent
from typing import TYPE_CHECKING, Any, Callable
from urllib.parse import parse_qs, unquote, urlparse

import click

from mycli.config import str_to_bool
from mycli.constants import EMPTY_PASSWORD_FLAG_SENTINEL, ISSUES_URL, REPO_URL
from mycli.main_modes.batch import main_batch_from_stdin, main_batch_with_progress_bar, main_batch_without_progress_bar
from mycli.main_modes.checkup import main_checkup
from mycli.main_modes.execute import main_execute_from_cli
from mycli.main_modes.list_dsn import main_list_dsn
from mycli.main_modes.list_ssh_config import main_list_ssh_config
from mycli.packages.cli_utils import is_valid_connection_scheme
from mycli.packages.ssh_utils import read_ssh_config

if TYPE_CHECKING:
    from mycli.main import CliArgs

ClientFactory = Callable[..., Any]
ENV_VAR_PATTERN = re.compile(r'^\$\{([A-Za-z_][A-Za-z0-9_]*)\}$')


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

    params = {key: [expand_dsn_alias_env_var(value, alias_name) or '' for value in values] for key, values in parse_qs(uri.query).items()}

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
        defaults_suffix=cli_args.defaults_group_suffix,
        defaults_file=cli_args.defaults_file,
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

    # ssh_port and ssh_config_path have truthy defaults and are not included
    if (
        any([
            cli_args.ssh_user,
            cli_args.ssh_host,
            cli_args.ssh_password,
            cli_args.ssh_key_filename,
            cli_args.list_ssh_config,
            cli_args.ssh_config_host,
        ])
        and not cli_args.ssh_warning_off
    ):
        click.secho(
            f"Warning: The built-in SSH functionality is deprecated and will be removed in a future release. See issue {ISSUES_URL}/1464",
            err=True,
            fg="red",
        )

    if cli_args.list_dsn:
        sys.exit(main_list_dsn(mycli))

    if cli_args.list_ssh_config:
        sys.exit(main_list_ssh_config(mycli, cli_args))

    # Choose which ever one has a valid value.
    database = cli_args.dbname or cli_args.database

    dsn_uri = None

    # Treat the database argument as a DSN alias only if it matches a configured alias
    # todo why is port tested but not socket?
    truthy_password = cli_args.password not in (None, EMPTY_PASSWORD_FLAG_SENTINEL)
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
            dsn_params = parse_qs(uri.query) if uri.query else {}

        if not database:
            database = dsn_database
        if not cli_args.user and dsn_user is not None:
            cli_args.user = dsn_user
        # todo: rationalize the behavior of empty-string passwords here
        if not cli_args.password and dsn_password is not None:
            cli_args.password = dsn_password
        if not cli_args.host:
            cli_args.host = dsn_host
        if not cli_args.port:
            cli_args.port = dsn_port

        if params := dsn_params.get('ssl'):
            click.secho(
                'Warning: The "ssl" DSN URI parameter is deprecated and will be removed in a future release. '
                'Please use the "ssl_mode" parameter instead. '
                f'See issue {ISSUES_URL}/1507',
                err=True,
                fg='yellow',
            )
            if params[0].lower() == 'true':
                cli_args.ssl_mode = 'on'
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

    if cli_args.ssh_config_host:
        ssh_config = read_ssh_config(cli_args.ssh_config_path).lookup(cli_args.ssh_config_host)
        ssh_host = cli_args.ssh_host if cli_args.ssh_host else ssh_config.get("hostname")
        ssh_user = cli_args.ssh_user if cli_args.ssh_user else ssh_config.get("user")
        if ssh_config.get("port") and cli_args.ssh_port == 22:
            # port has a default value, overwrite it if it's in the config
            ssh_port = int(ssh_config.get("port"))
        else:
            ssh_port = cli_args.ssh_port
        ssh_key_filename = cli_args.ssh_key_filename if cli_args.ssh_key_filename else ssh_config.get("identityfile", [None])[0]
    else:
        ssh_host = cli_args.ssh_host
        ssh_user = cli_args.ssh_user
        ssh_port = cli_args.ssh_port
        ssh_key_filename = cli_args.ssh_key_filename

    ssh_key_filename = ssh_key_filename and os.path.expanduser(ssh_key_filename)
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
    elif cli_args.use_keyring is None:
        use_keyring = str_to_bool(mycli.config['main'].get('use_keyring', 'False'))
        reset_keyring = False
    else:
        use_keyring = str_to_bool(cli_args.use_keyring)
        reset_keyring = False

    # todo: removeme after a period of transition
    for tup in [
        ('client', 'prompt', 'prompt', 'main', 'prompt'),
        ('client', 'pager', 'pager', 'main', 'pager'),
        ('client', 'skip-pager', 'skip-pager', 'main', 'enable_pager'),
        # this is a white lie, because default_character_set can actually be read from the package config
        ('client', 'default-character-set', 'default-character-set', 'connection', 'default_character_set'),
        # local-infile can be read from both sections
        ('mysqld', 'local-infile', 'local-infile', 'connection', 'default_local_infile'),
        ('client', 'local-infile', 'local-infile', 'connection', 'default_local_infile'),
        ('mysqld', 'loose-local-infile', 'loose-local-infile', 'connection', 'default_local_infile'),
        ('client', 'loose-local-infile', 'loose-local-infile', 'connection', 'default_local_infile'),
        # todo: in the future we should add default_port, etc, but only in .myclirc
        # they are currently ignored in my.cnf
        ('mysqld', 'default_socket', 'socket', 'connection', 'default_socket'),
        ('client', 'ssl-ca', 'ssl-ca', 'connection', 'default_ssl_ca'),
        ('client', 'ssl-cert', 'ssl-cert', 'connection', 'default_ssl_cert'),
        ('client', 'ssl-key', 'ssl-key', 'connection', 'default_ssl_key'),
        ('client', 'ssl-cipher', 'ssl-cipher', 'connection', 'default_ssl_cipher'),
        ('client', 'ssl-verify-server-cert', 'ssl-verify-server-cert', 'connection', 'default_ssl_verify_server_cert'),
    ]:
        (
            mycnf_section_name,
            mycnf_item_name,
            printable_mycnf_item_name,
            myclirc_section_name,
            myclirc_item_name,
        ) = tup
        if str_to_bool(mycli.config['main'].get('my_cnf_transition_done', 'False')):
            break
        if (
            mycli.my_cnf[mycnf_section_name].get(mycnf_item_name) is None
            and mycli.my_cnf[mycnf_section_name].get(mycnf_item_name.replace('-', '_')) is None
        ):
            continue
        user_section = mycli.config_without_package_defaults.get(myclirc_section_name, {})
        if user_section.get(myclirc_item_name) is None:
            cnf_value = mycli.my_cnf[mycnf_section_name].get(mycnf_item_name)
            if cnf_value is None:
                cnf_value = mycli.my_cnf[mycnf_section_name].get(mycnf_item_name.replace('-', '_'))
            click.secho(
                dedent(
                    f"""
                    Reading configuration from my.cnf files is deprecated.
                    See {ISSUES_URL}/1490 .
                    The cause of this message is the following in a my.cnf file without a corresponding
                    ~/.myclirc entry:

                        [{mycnf_section_name}]
                        {printable_mycnf_item_name} = {cnf_value}

                    To suppress this message, remove the my.cnf item add or the following to ~/.myclirc:

                        [{myclirc_section_name}]
                        {myclirc_item_name} = <value>

                    The ~/.myclirc setting will take precedence.  In the future, the my.cnf will be ignored.

                    Values are documented at {REPO_URL}/blob/main/mycli/myclirc .  An
                    empty <value> is generally accepted.

                    To ignore all of this, set

                        [main]
                        my_cnf_transition_done = True

                    in ~/.myclirc.

                    --------

                    """
                ),
                err=True,
                fg='yellow',
            )

    mycli.connect(
        database=database,
        user=cli_args.user,
        passwd=cli_args.password,
        host=cli_args.host,
        port=cli_args.port,
        socket=cli_args.socket,
        local_infile=cli_args.local_infile,
        ssl=ssl,
        ssh_user=ssh_user,
        ssh_host=ssh_host,
        ssh_port=ssh_port,
        ssh_password=cli_args.ssh_password,
        ssh_key_filename=ssh_key_filename,
        init_command=combined_init_cmd,
        unbuffered=cli_args.unbuffered,
        character_set=cli_args.character_set,
        use_keyring=use_keyring,
        reset_keyring=reset_keyring,
        keepalive_ticks=keepalive_ticks,
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
    mycli.close()
