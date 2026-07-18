from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from mycli import cli_runner, main
from mycli.password_sources import (
    KNOWN_PASSWORD_SOURCES,
)


class DummyLogger:
    def __init__(self) -> None:
        self.debug_calls: list[tuple[tuple[Any, ...], dict[str, Any]]] = []

    def debug(self, *args: Any, **kwargs: Any) -> None:
        self.debug_calls.append((args, kwargs))


class DummyMyCli:
    def __init__(
        self,
        *,
        config: dict[str, Any] | None = None,
        my_cnf: dict[str, Any] | None = None,
        config_without_package_defaults: dict[str, Any] | None = None,
    ) -> None:
        self.config = config or default_config()
        self.my_cnf = my_cnf or {'client': {}, 'mysqld': {}}
        self.config_without_package_defaults = config_without_package_defaults or {}
        self.default_keepalive_ticks = 5
        self.ssl_mode: str | None = None
        self.logger = DummyLogger()
        self.dsn_alias: str | None = None
        self.ssh_tunnel: Any = None
        self.connect_calls: list[dict[str, Any]] = []
        self.run_cli_called = False
        self.close_called = False

    def connect(self, **kwargs: Any) -> None:
        self.connect_calls.append(dict(kwargs))

    def run_cli(self) -> None:
        self.run_cli_called = True

    def close(self) -> None:
        if getattr(self, 'ssh_tunnel', None) is not None:
            self.ssh_tunnel.close()
        self.close_called = True


def default_config() -> dict[str, Any]:
    return {
        'main': {'use_keyring': 'false'},
        'connection': {'default_keepalive_ticks': 0},
        'vault_beta': {},
        'alias_dsn': {},
        'init-commands': {},
        'alias_dsn.init-commands': {},
    }


def make_cli_args() -> main.CliArgs:
    cli_args = main.CliArgs()
    cli_args.format = None
    return cli_args


def run_with_client(
    monkeypatch: pytest.MonkeyPatch,
    cli_args: main.CliArgs,
    client: DummyMyCli,
) -> DummyMyCli:
    monkeypatch.setattr(main, 'preprocess_cli_args', lambda args, scheme_validator: 4)
    monkeypatch.setattr(cli_runner.sys, 'stdin', SimpleNamespace(isatty=lambda: True))
    monkeypatch.setattr(cli_runner.sys.stderr, 'isatty', lambda: False)
    cli_runner.run_from_cli_args(cli_args, lambda **_kwargs: client)
    return client


def resolve_connect_password(connect_call: dict[str, Any]) -> tuple[str, str | int] | None:
    selected = connect_call['password_candidates'].resolve(KNOWN_PASSWORD_SOURCES)
    if selected is None:
        return None
    return selected.source, selected.value


def test_expand_dsn_alias_env_var_returns_none() -> None:
    assert cli_runner.expand_dsn_alias_env_var(None, 'prod') is None


def test_split_dsn_netloc_handles_user_without_password() -> None:
    assert cli_runner.split_dsn_netloc('user@host:3306') == ('user', None, 'host', '3306')


def test_split_dsn_netloc_handles_empty_host() -> None:
    assert cli_runner.split_dsn_netloc('user:pass@') == ('user', 'pass', None, None)


def test_split_dsn_netloc_handles_bracketed_ipv6_host() -> None:
    assert cli_runner.split_dsn_netloc('user:pass@[::1]:3306') == ('user', 'pass', '::1', '3306')


def test_expand_dsn_alias_env_vars_rejects_non_integer_port(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv('MYCLI_TEST_DSN_PORT', 'not-an-int')

    with pytest.raises(cli_runner.DsnAliasEnvVarError) as excinfo:
        cli_runner.expand_dsn_alias_env_vars('mysql://user:pass@host:${MYCLI_TEST_DSN_PORT}/db', 'prod')

    assert str(excinfo.value) == 'Port in DSN alias prod must be an integer.'


def test_run_from_cli_args_checkup_exits_zero(monkeypatch: pytest.MonkeyPatch) -> None:
    cli_args = make_cli_args()
    cli_args.checkup = True
    client = DummyMyCli()
    checkup_calls: list[DummyMyCli] = []
    monkeypatch.setattr(cli_runner, 'main_checkup', lambda value: checkup_calls.append(value))
    monkeypatch.setattr(main, 'preprocess_cli_args', lambda args, scheme_validator: 0)

    with pytest.raises(SystemExit) as excinfo:
        cli_runner.run_from_cli_args(cli_args, lambda **_kwargs: client)

    assert excinfo.value.code == 0
    assert checkup_calls == [client]


@pytest.mark.parametrize(
    ('csv', 'table', 'format_name', 'message'),
    (
        (True, False, 'table', 'Conflicting --csv and --format arguments.'),
        (False, True, 'csv', 'Conflicting --table and --format arguments.'),
    ),
)
def test_run_from_cli_args_rejects_conflicting_format_flags(
    monkeypatch: pytest.MonkeyPatch,
    csv: bool,
    table: bool,
    format_name: str,
    message: str,
) -> None:
    cli_args = make_cli_args()
    cli_args.csv = csv
    cli_args.table = table
    cli_args.format = format_name
    secho_calls: list[tuple[str, dict[str, Any]]] = []
    monkeypatch.setattr(cli_runner.click, 'secho', lambda text, **kwargs: secho_calls.append((text, kwargs)))
    monkeypatch.setattr(main, 'preprocess_cli_args', lambda args, scheme_validator: 0)

    with pytest.raises(SystemExit) as excinfo:
        cli_runner.run_from_cli_args(cli_args, lambda **_kwargs: DummyMyCli())

    assert excinfo.value.code == 1
    assert secho_calls == [(message, {'err': True, 'fg': 'red'})]


def test_run_from_cli_args_treats_database_as_dsn_alias(monkeypatch: pytest.MonkeyPatch) -> None:
    cli_args = make_cli_args()
    cli_args.database = 'prod'
    client = DummyMyCli(
        config={
            **default_config(),
            'alias_dsn': {'prod': 'mysql://u:p@h/db'},
        }
    )

    run_with_client(monkeypatch, cli_args, client)

    assert client.dsn_alias == 'prod'
    connect_call = client.connect_calls[-1]
    assert connect_call['user'] == 'u'
    assert resolve_connect_password(connect_call) == ('dsn', 'p')
    assert connect_call['host'] == 'h'
    assert connect_call['database'] == 'db'


def test_run_from_cli_args_password_file_prevents_positional_dsn_alias(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cli_args = make_cli_args()
    cli_args.database = 'prod'
    cli_args.password_file = 'secret.txt'
    client = DummyMyCli(
        config={
            **default_config(),
            'alias_dsn': {'prod': 'mysql://u:p@h/db'},
        }
    )
    password_file_calls: list[str | None] = []

    def read_password_file(password_file: str | None) -> str:
        password_file_calls.append(password_file)
        return 'file-secret'

    monkeypatch.setattr(main, 'get_password_from_file', read_password_file)

    run_with_client(monkeypatch, cli_args, client)

    connect_call = client.connect_calls[-1]
    assert client.dsn_alias is None
    assert connect_call['database'] == 'prod'
    assert resolve_connect_password(connect_call) == ('file', 'file-secret')
    assert password_file_calls == ['secret.txt']


def test_run_from_cli_args_mysql_pwd_prevents_positional_dsn_alias(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cli_args = make_cli_args()
    cli_args.database = 'prod'
    client = DummyMyCli(
        config={
            **default_config(),
            'alias_dsn': {'prod': 'mysql://u:p@h/db'},
        }
    )
    monkeypatch.setenv('MYSQL_PWD', 'environment-secret')

    run_with_client(monkeypatch, cli_args, client)

    connect_call = client.connect_calls[-1]
    assert client.dsn_alias is None
    assert connect_call['database'] == 'prod'
    assert resolve_connect_password(connect_call) == ('environment', 'environment-secret')


def test_run_from_cli_args_keeps_empty_cli_password_over_dsn(monkeypatch: pytest.MonkeyPatch) -> None:
    cli_args = make_cli_args()
    cli_args.dsn = 'mysql://user:dsn-secret@host/db'
    cli_args.password = ''
    client = DummyMyCli()

    run_with_client(monkeypatch, cli_args, client)

    assert resolve_connect_password(client.connect_calls[-1]) == ('literal', '')


def test_run_from_cli_args_preserves_cli_password_prompt(monkeypatch: pytest.MonkeyPatch) -> None:
    cli_args = make_cli_args()
    cli_args.password = cli_runner.EMPTY_PASSWORD_FLAG_SENTINEL
    client = DummyMyCli()

    run_with_client(monkeypatch, cli_args, client)

    assert resolve_connect_password(client.connect_calls[-1]) == (
        'prompt',
        cli_runner.EMPTY_PASSWORD_FLAG_SENTINEL,
    )


def test_run_from_cli_args_leaves_dsn_alias_env_vars_disabled_by_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cli_args = make_cli_args()
    cli_args.dsn = 'prod'
    monkeypatch.setenv('MYCLI_TEST_DSN_USER', 'env_user')
    client = DummyMyCli(
        config={
            **default_config(),
            'alias_dsn': {'prod': 'mysql://${MYCLI_TEST_DSN_USER}:pass@host:3306/db'},
        }
    )

    run_with_client(monkeypatch, cli_args, client)

    assert client.connect_calls[-1]['user'] == '${MYCLI_TEST_DSN_USER}'


def test_run_from_cli_args_expands_whole_dsn_alias_env_vars_when_enabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cli_args = make_cli_args()
    cli_args.dsn = 'prod'
    monkeypatch.setenv('MYCLI_TEST_DSN_USER', 'env_user')
    monkeypatch.setenv('MYCLI_TEST_DSN_PASSWORD', 'env_pass')
    monkeypatch.setenv('MYCLI_TEST_DSN_HOST', 'env-host')
    monkeypatch.setenv('MYCLI_TEST_DSN_PORT', '3308')
    monkeypatch.setenv('MYCLI_TEST_DSN_DATABASE', 'env_db')
    monkeypatch.setenv('MYCLI_TEST_DSN_CHARSET', 'utf8mb4')
    monkeypatch.setenv('MYCLI_TEST_DSN_KEEPALIVE', '9')
    config = default_config()
    config['main'] = {**config['main'], 'expand_dsn_alias_env_vars': 'true'}
    config['alias_dsn'] = {
        'prod': (
            'mysql://${MYCLI_TEST_DSN_USER}:${MYCLI_TEST_DSN_PASSWORD}'
            '@${MYCLI_TEST_DSN_HOST}:${MYCLI_TEST_DSN_PORT}/${MYCLI_TEST_DSN_DATABASE}'
            '?character_set=${MYCLI_TEST_DSN_CHARSET}&keepalive_ticks=${MYCLI_TEST_DSN_KEEPALIVE}'
        )
    }
    client = DummyMyCli(config=config)

    run_with_client(monkeypatch, cli_args, client)

    assert client.connect_calls[-1]['user'] == 'env_user'
    assert resolve_connect_password(client.connect_calls[-1]) == ('dsn', 'env_pass')
    assert client.connect_calls[-1]['host'] == 'env-host'
    assert client.connect_calls[-1]['port'] == 3308
    assert client.connect_calls[-1]['database'] == 'env_db'
    assert client.connect_calls[-1]['character_set'] == 'utf8mb4'
    assert client.connect_calls[-1]['keepalive_ticks'] == 9


def test_run_from_cli_args_expands_dsn_alias_ssh_jump_env_var_when_enabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cli_args = make_cli_args()
    cli_args.dsn = 'prod'
    monkeypatch.setenv('MYCLI_TEST_DSN_SSH_JUMP', 'env-bastion')
    config = default_config()
    config['main'] = {**config['main'], 'expand_dsn_alias_env_vars': 'true'}
    config['alias_dsn'] = {'prod': 'mysql://user@host/db?ssh_jump=${MYCLI_TEST_DSN_SSH_JUMP}'}
    client = DummyMyCli(config=config)

    run_with_client(monkeypatch, cli_args, client)

    assert client.connect_calls[-1]['ssh_jump'] == 'env-bastion'


def test_run_from_cli_args_does_not_expand_partial_values_or_query_keys(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cli_args = make_cli_args()
    cli_args.dsn = 'prod'
    monkeypatch.setenv('MYCLI_TEST_DSN_USER', 'env_user')
    monkeypatch.setenv('MYCLI_TEST_DSN_QUERY_KEY', 'character_set')
    config = default_config()
    config['main'] = {**config['main'], 'expand_dsn_alias_env_vars': 'true'}
    config['alias_dsn'] = {
        'prod': ('mysql://user-${MYCLI_TEST_DSN_USER}:pass@host:3306/db?${MYCLI_TEST_DSN_QUERY_KEY}=utf8mb4&character_set=utf8')
    }
    client = DummyMyCli(config=config)

    run_with_client(monkeypatch, cli_args, client)

    assert client.connect_calls[-1]['user'] == 'user-${MYCLI_TEST_DSN_USER}'
    assert client.connect_calls[-1]['character_set'] == 'utf8'


def test_run_from_cli_args_does_not_expand_unbraced_dsn_alias_env_vars(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cli_args = make_cli_args()
    cli_args.dsn = 'prod'
    monkeypatch.setenv('MYCLI_TEST_DSN_USER', 'env_user')
    config = default_config()
    config['main'] = {**config['main'], 'expand_dsn_alias_env_vars': 'true'}
    config['alias_dsn'] = {'prod': 'mysql://$MYCLI_TEST_DSN_USER:pass@host:3306/db'}
    client = DummyMyCli(config=config)

    run_with_client(monkeypatch, cli_args, client)

    assert client.connect_calls[-1]['user'] == '$MYCLI_TEST_DSN_USER'


def test_run_from_cli_args_warns_about_unknown_dsn_query_parameter(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cli_args = make_cli_args()
    cli_args.dsn = 'mysql://user@host/db?unknown=value'
    client = DummyMyCli()
    secho_calls: list[tuple[str, dict[str, Any]]] = []
    monkeypatch.setattr(cli_runner.click, 'secho', lambda text, **kwargs: secho_calls.append((text, kwargs)))

    run_with_client(monkeypatch, cli_args, client)

    assert client.connect_calls[-1]['database'] == 'db'
    assert secho_calls == [
        (
            'Warning: Ignored unknown DSN URI query parameters: unknown.',
            {'err': True, 'fg': 'yellow'},
        )
    ]


def test_run_from_cli_args_warns_once_about_sorted_unknown_dsn_query_parameters(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cli_args = make_cli_args()
    cli_args.dsn = 'mysql://user@host/db?zzz=1&aaa&character_set=utf8&aaa=2'
    client = DummyMyCli()
    secho_calls: list[tuple[str, dict[str, Any]]] = []
    monkeypatch.setattr(cli_runner.click, 'secho', lambda text, **kwargs: secho_calls.append((text, kwargs)))

    run_with_client(monkeypatch, cli_args, client)

    assert client.connect_calls[-1]['character_set'] == 'utf8'
    assert secho_calls == [
        (
            'Warning: Ignored unknown DSN URI query parameters: aaa, zzz.',
            {'err': True, 'fg': 'yellow'},
        )
    ]


def test_run_from_cli_args_warns_about_unknown_alias_dsn_query_parameter_with_env_expansion(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cli_args = make_cli_args()
    cli_args.dsn = 'prod'
    monkeypatch.setenv('MYCLI_TEST_DSN_CHARSET', 'utf8')
    config = default_config()
    config['main'] = {**config['main'], 'expand_dsn_alias_env_vars': 'true'}
    config['alias_dsn'] = {'prod': 'mysql://user@host/db?unknown=value&character_set=${MYCLI_TEST_DSN_CHARSET}'}
    client = DummyMyCli(config=config)
    secho_calls: list[tuple[str, dict[str, Any]]] = []
    monkeypatch.setattr(cli_runner.click, 'secho', lambda text, **kwargs: secho_calls.append((text, kwargs)))

    run_with_client(monkeypatch, cli_args, client)

    assert client.connect_calls[-1]['character_set'] == 'utf8'
    assert secho_calls == [
        (
            'Warning: Ignored unknown DSN URI query parameters: unknown.',
            {'err': True, 'fg': 'yellow'},
        )
    ]


def test_run_from_cli_args_reports_missing_dsn_alias_env_var(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cli_args = make_cli_args()
    cli_args.dsn = 'prod'
    config = default_config()
    config['main'] = {**config['main'], 'expand_dsn_alias_env_vars': 'true'}
    config['alias_dsn'] = {'prod': 'mysql://${MYCLI_TEST_MISSING_DSN_USER}:pass@host:3306/db'}
    client = DummyMyCli(config=config)
    secho_calls: list[tuple[str, dict[str, Any]]] = []
    monkeypatch.setattr(cli_runner.click, 'secho', lambda text, **kwargs: secho_calls.append((text, kwargs)))

    with pytest.raises(SystemExit) as excinfo:
        run_with_client(monkeypatch, cli_args, client)

    assert excinfo.value.code == 1
    assert secho_calls == [
        (
            'Environment variable MYCLI_TEST_MISSING_DSN_USER referenced by DSN alias prod is not set.',
            {'err': True, 'fg': 'red'},
        )
    ]
    assert client.connect_calls == []


def test_run_from_cli_args_reports_missing_dsn(monkeypatch: pytest.MonkeyPatch) -> None:
    cli_args = make_cli_args()
    cli_args.dsn = 'missing'
    secho_calls: list[tuple[str, dict[str, Any]]] = []
    monkeypatch.setattr(cli_runner, 'is_valid_connection_scheme', lambda value: (False, None))
    monkeypatch.setattr(cli_runner.click, 'secho', lambda text, **kwargs: secho_calls.append((text, kwargs)))
    monkeypatch.setattr(main, 'preprocess_cli_args', lambda args, scheme_validator: 0)

    with pytest.raises(SystemExit) as excinfo:
        cli_runner.run_from_cli_args(cli_args, lambda **_kwargs: DummyMyCli())

    assert excinfo.value.code == 1
    assert secho_calls == [
        (
            'Could not find the specified DSN in the config file. Please check the "[alias_dsn]" section in your myclirc.',
            {'err': True, 'fg': 'red'},
        )
    ]


def test_run_from_cli_args_rejects_unknown_positional_dsn_scheme(monkeypatch: pytest.MonkeyPatch) -> None:
    cli_args = make_cli_args()
    cli_args.database = 'ssh://user@example.com/db'
    secho_calls: list[tuple[str, dict[str, Any]]] = []
    monkeypatch.setattr(cli_runner.click, 'secho', lambda text, **kwargs: secho_calls.append((text, kwargs)))

    with pytest.raises(SystemExit) as excinfo:
        run_with_client(monkeypatch, cli_args, DummyMyCli())

    assert excinfo.value.code == 1
    assert secho_calls == [
        (
            'Error: Unknown connection scheme provided for DSN URI (ssh://)',
            {'err': True, 'fg': 'red'},
        )
    ]


def test_run_from_cli_args_rejects_unknown_alias_dsn_scheme(monkeypatch: pytest.MonkeyPatch) -> None:
    cli_args = make_cli_args()
    cli_args.dsn = 'legacy_ssh'
    client = DummyMyCli(
        config={
            **default_config(),
            'alias_dsn': {'legacy_ssh': 'ssh://user@example.com/db'},
        }
    )
    secho_calls: list[tuple[str, dict[str, Any]]] = []
    monkeypatch.setattr(cli_runner.click, 'secho', lambda text, **kwargs: secho_calls.append((text, kwargs)))

    with pytest.raises(SystemExit) as excinfo:
        run_with_client(monkeypatch, cli_args, client)

    assert excinfo.value.code == 1
    assert secho_calls == [
        (
            'Error: Unknown connection scheme provided for DSN URI (ssh://)',
            {'err': True, 'fg': 'red'},
        )
    ]


def test_run_from_cli_args_accepts_mysql_plus_dsn_scheme(monkeypatch: pytest.MonkeyPatch) -> None:
    cli_args = make_cli_args()
    cli_args.dsn = 'mysql+pymysql://user:pass@host:3306/db'
    client = DummyMyCli()

    run_with_client(monkeypatch, cli_args, client)

    assert client.connect_calls[-1]['user'] == 'user'
    assert resolve_connect_password(client.connect_calls[-1]) == ('dsn', 'pass')
    assert client.connect_calls[-1]['host'] == 'host'
    assert client.connect_calls[-1]['port'] == 3306
    assert client.connect_calls[-1]['database'] == 'db'


def test_run_from_cli_args_maps_dsn_ssh_jump_parameter(monkeypatch: pytest.MonkeyPatch) -> None:
    cli_args = make_cli_args()
    cli_args.dsn = 'mysql://user@host/db?ssh_jump=bastion'
    client = DummyMyCli()

    run_with_client(monkeypatch, cli_args, client)

    assert client.connect_calls[-1]['ssh_jump'] == 'bastion'


def test_run_from_cli_args_does_not_warn_about_known_dsn_query_parameter(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cli_args = make_cli_args()
    cli_args.dsn = 'mysql://user@host/db?ssh_jump=bastion'
    client = DummyMyCli()
    secho_calls: list[tuple[str, dict[str, Any]]] = []
    monkeypatch.setattr(cli_runner.click, 'secho', lambda text, **kwargs: secho_calls.append((text, kwargs)))

    run_with_client(monkeypatch, cli_args, client)

    assert client.connect_calls[-1]['ssh_jump'] == 'bastion'
    assert secho_calls == []


def test_run_from_cli_args_prefers_cli_ssh_jump_over_dsn_parameter(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cli_args = make_cli_args()
    cli_args.dsn = 'mysql://user@host/db?ssh_jump=dsn-bastion'
    cli_args.ssh_jump = 'cli-bastion'
    client = DummyMyCli()

    run_with_client(monkeypatch, cli_args, client)

    assert client.connect_calls[-1]['ssh_jump'] == 'cli-bastion'


def test_run_from_cli_args_maps_dsn_ssl_parameters(monkeypatch: pytest.MonkeyPatch) -> None:
    cli_args = make_cli_args()
    cli_args.dsn = (
        'mysql://user:pass@host:3306/db?ssl_mode=on&ssl_ca=~/ca.pem&ssl_capath=/capath'
        '&ssl_cert=~/cert.pem&ssl_key=~/key.pem&ssl_cipher=AES256&tls_version=TLSv1.3'
        '&ssl_verify_server_cert=true'
    )
    client = DummyMyCli()
    secho_calls: list[str] = []
    monkeypatch.setattr(cli_runner.click, 'secho', lambda text, **_kwargs: secho_calls.append(text))

    run_with_client(monkeypatch, cli_args, client)

    ssl = client.connect_calls[-1]['ssl']
    assert ssl == {
        'mode': 'on',
        'ca': cli_runner.os.path.expanduser('~/ca.pem'),
        'capath': '/capath',
        'cert': cli_runner.os.path.expanduser('~/cert.pem'),
        'key': cli_runner.os.path.expanduser('~/key.pem'),
        'cipher': 'AES256',
        'tls_version': 'TLSv1.3',
        'check_hostname': True,
    }


def test_run_from_cli_args_merges_global_list_and_alias_scalar_init_commands(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cli_args = make_cli_args()
    cli_args.dsn = 'prod'
    cli_args.init_command = 'set cli=1'
    client = DummyMyCli(
        config={
            **default_config(),
            'alias_dsn': {'prod': 'mysql://u:p@h/db'},
            'init-commands': {'first': ['set global=1', 'set global=2']},
            'alias_dsn.init-commands': {'prod': 'set alias=1'},
        }
    )

    run_with_client(monkeypatch, cli_args, client)

    assert client.connect_calls[-1]['init_command'] == 'set global=1; set global=2; set alias=1; set cli=1'


def test_run_from_cli_args_resets_keyring(monkeypatch: pytest.MonkeyPatch) -> None:
    cli_args = make_cli_args()
    cli_args.use_keyring = 'reset'
    client = DummyMyCli()

    run_with_client(monkeypatch, cli_args, client)

    assert client.connect_calls[-1]['use_keyring'] is True
    assert client.connect_calls[-1]['reset_keyring'] is True


def test_run_from_cli_args_uses_explicit_keyring_flag(monkeypatch: pytest.MonkeyPatch) -> None:
    cli_args = make_cli_args()
    cli_args.use_keyring = 'true'
    client = DummyMyCli()

    run_with_client(monkeypatch, cli_args, client)

    assert client.connect_calls[-1]['use_keyring'] is True
    assert client.connect_calls[-1]['reset_keyring'] is False


def test_run_from_cli_args_reads_password_from_vault_when_password_is_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cli_args = make_cli_args()
    cli_args.user = 'existing-user'
    cli_args.vault_secret = 'database/prod'
    client = DummyMyCli(
        config={
            **default_config(),
            'vault_beta': {
                'vault_executable': '/opt/bin/vault',
                'address': 'https://vault.config',
                'default_mount': 'kv',
                'default_password_field': 'mysql_password',
            },
        }
    )
    vault_calls: list[dict[str, str | None]] = []

    def fake_get_field_from_vault(field: str, secret: str, **kwargs: str | None) -> str:
        vault_calls.append({'field': field, 'secret': secret, **kwargs})
        return 'vault-secret'

    monkeypatch.delenv('VAULT_ADDR', raising=False)
    monkeypatch.setattr(cli_runner, 'get_field_from_vault', fake_get_field_from_vault)

    run_with_client(monkeypatch, cli_args, client)

    assert resolve_connect_password(client.connect_calls[-1]) == ('vault', 'vault-secret')
    assert vault_calls == [
        {
            'secret': 'database/prod',
            'executable': '/opt/bin/vault',
            'field': 'mysql_password',
            'mount': 'kv',
            'address': 'https://vault.config',
        }
    ]


def test_run_from_cli_args_reads_username_from_vault_when_user_is_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cli_args = make_cli_args()
    cli_args.password = 'existing-password'
    cli_args.vault_secret = 'database/prod'
    cli_args.vault_username_field = 'mysql_username'
    client = DummyMyCli(
        config={
            **default_config(),
            'vault_beta': {
                'vault_executable': '/opt/bin/vault',
                'address': 'https://vault.config',
                'default_mount': 'kv',
            },
        }
    )
    vault_calls: list[dict[str, str | None]] = []

    def fake_get_field_from_vault(field: str, secret: str, **kwargs: str | None) -> str:
        vault_calls.append({'field': field, 'secret': secret, **kwargs})
        return 'vault-user'

    monkeypatch.delenv('VAULT_ADDR', raising=False)
    monkeypatch.setattr(cli_runner, 'get_field_from_vault', fake_get_field_from_vault)

    run_with_client(monkeypatch, cli_args, client)

    assert client.connect_calls[-1]['user'] == 'vault-user'
    assert client.connect_calls[-1]['vault_username_from_vault'] is True
    assert vault_calls == [
        {
            'secret': 'database/prod',
            'executable': '/opt/bin/vault',
            'field': 'mysql_username',
            'mount': 'kv',
            'address': 'https://vault.config',
        }
    ]


def test_run_from_cli_args_prefers_dsn_user_over_vault_username(monkeypatch: pytest.MonkeyPatch) -> None:
    cli_args = make_cli_args()
    cli_args.dsn = 'mysql://dsn-user@host/db'
    cli_args.password = 'existing-password'
    cli_args.vault_secret = 'database/prod'
    cli_args.vault_username_field = 'mysql_username'
    client = DummyMyCli()
    vault_calls: list[dict[str, str | None]] = []

    def fake_get_field_from_vault(field: str, secret: str, **kwargs: str | None) -> str:
        vault_calls.append({'field': field, 'secret': secret, **kwargs})
        return 'vault-user'

    monkeypatch.setattr(cli_runner, 'get_field_from_vault', fake_get_field_from_vault)

    run_with_client(monkeypatch, cli_args, client)

    assert client.connect_calls[-1]['user'] == 'dsn-user'
    assert client.connect_calls[-1]['vault_username_from_vault'] is False
    assert vault_calls == []


def test_run_from_cli_args_reports_vault_username_error(monkeypatch: pytest.MonkeyPatch) -> None:
    cli_args = make_cli_args()
    cli_args.password = 'existing-password'
    cli_args.vault_secret = 'database/prod'
    cli_args.vault_username_field = 'mysql_username'
    client = DummyMyCli()
    secho_calls: list[tuple[str, dict[str, Any]]] = []
    monkeypatch.setattr(cli_runner.click, 'secho', lambda text, **kwargs: secho_calls.append((text, kwargs)))
    monkeypatch.setattr(
        cli_runner,
        'get_field_from_vault',
        lambda *_args, **_kwargs: (_ for _ in ()).throw(cli_runner.VaultError('permission denied')),
    )

    with pytest.raises(SystemExit) as excinfo:
        run_with_client(monkeypatch, cli_args, client)

    assert excinfo.value.code == 1
    assert client.connect_calls == []
    assert secho_calls == [('Error reading username from Vault: permission denied', {'err': True, 'fg': 'red'})]


def test_run_from_cli_args_prefers_dsn_password_over_vault(monkeypatch: pytest.MonkeyPatch) -> None:
    cli_args = make_cli_args()
    cli_args.dsn = 'mysql://user:dsn-secret@host/db'
    cli_args.vault_secret = 'database/prod'
    client = DummyMyCli()
    vault_calls: list[dict[str, str | None]] = []

    def fake_get_field_from_vault(field: str, secret: str, **kwargs: str | None) -> str:
        vault_calls.append({'field': field, 'secret': secret, **kwargs})
        return 'vault-secret'

    monkeypatch.setattr(cli_runner, 'get_field_from_vault', fake_get_field_from_vault)

    run_with_client(monkeypatch, cli_args, client)

    assert resolve_connect_password(client.connect_calls[-1]) == ('dsn', 'dsn-secret')
    assert vault_calls == []


def test_run_from_cli_args_prefers_vault_cli_values_and_env_address(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cli_args = make_cli_args()
    cli_args.user = 'existing-user'
    cli_args.vault_secret = 'database/prod'
    cli_args.vault_mount = 'cli-mount'
    cli_args.vault_password_field = 'cli-field'
    client = DummyMyCli(
        config={
            **default_config(),
            'vault_beta': {
                'vault_executable': '/opt/bin/vault',
                'address': 'https://vault.config',
                'default_mount': 'config-mount',
                'default_password_field': 'config-field',
            },
        }
    )
    vault_calls: list[dict[str, str | None]] = []
    monkeypatch.setenv('VAULT_ADDR', 'https://vault.env')

    def fake_get_field_from_vault(field: str, secret: str, **kwargs: str | None) -> str:
        vault_calls.append({'field': field, 'secret': secret, **kwargs})
        return 'vault-secret'

    monkeypatch.setattr(cli_runner, 'get_field_from_vault', fake_get_field_from_vault)

    run_with_client(monkeypatch, cli_args, client)

    assert resolve_connect_password(client.connect_calls[-1]) == ('vault', 'vault-secret')
    assert client.connect_calls[-1]['vault_username_from_vault'] is False
    assert vault_calls == [
        {
            'secret': 'database/prod',
            'executable': '/opt/bin/vault',
            'field': 'cli-field',
            'mount': 'cli-mount',
            'address': 'https://vault.env',
        }
    ]


def test_run_from_cli_args_prefers_vault_cli_address_over_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cli_args = make_cli_args()
    cli_args.user = 'existing-user'
    cli_args.vault_secret = 'database/prod'
    cli_args.vault_address = 'https://vault.cli'
    client = DummyMyCli()
    vault_calls: list[dict[str, str | None]] = []
    monkeypatch.setenv('VAULT_ADDR', 'https://vault.env')

    def fake_get_field_from_vault(field: str, secret: str, **kwargs: str | None) -> str:
        vault_calls.append({'field': field, 'secret': secret, **kwargs})
        return 'vault-secret'

    monkeypatch.setattr(cli_runner, 'get_field_from_vault', fake_get_field_from_vault)

    run_with_client(monkeypatch, cli_args, client)

    assert resolve_connect_password(client.connect_calls[-1]) == ('vault', 'vault-secret')
    assert vault_calls[-1]['address'] == 'https://vault.cli'


def test_run_from_cli_args_reports_vault_error(monkeypatch: pytest.MonkeyPatch) -> None:
    cli_args = make_cli_args()
    cli_args.user = 'existing-user'
    cli_args.vault_secret = 'database/prod'
    client = DummyMyCli()
    secho_calls: list[tuple[str, dict[str, Any]]] = []
    monkeypatch.setattr(cli_runner.click, 'secho', lambda text, **kwargs: secho_calls.append((text, kwargs)))
    monkeypatch.setattr(
        cli_runner,
        'get_field_from_vault',
        lambda *_args, **_kwargs: (_ for _ in ()).throw(cli_runner.VaultError('permission denied')),
    )

    run_with_client(monkeypatch, cli_args, client)

    with pytest.raises(SystemExit) as excinfo:
        resolve_connect_password(client.connect_calls[-1])

    assert excinfo.value.code == 1
    assert secho_calls == [('Error reading password from Vault: permission denied', {'err': True, 'fg': 'red'})]


def test_run_from_cli_args_passes_ssh_options_to_connect(monkeypatch: pytest.MonkeyPatch) -> None:
    cli_args = make_cli_args()
    cli_args.ssh_options = '-o Compression=yes'
    client = DummyMyCli()

    run_with_client(monkeypatch, cli_args, client)

    assert client.connect_calls[-1]['ssh_cli_options'] == '-o Compression=yes'


@pytest.mark.parametrize(
    ('ssh_connection', 'expected_use_keyring'),
    (
        (None, True),
        ('client-ip client-port server-ip server-port', False),
    ),
)
def test_run_from_cli_args_uses_auto_keyring_flag(
    monkeypatch: pytest.MonkeyPatch,
    ssh_connection: str | None,
    expected_use_keyring: bool,
) -> None:
    cli_args = make_cli_args()
    cli_args.use_keyring = 'auto'
    client = DummyMyCli()
    if ssh_connection is None:
        monkeypatch.delenv('SSH_CONNECTION', raising=False)
    else:
        monkeypatch.setenv('SSH_CONNECTION', ssh_connection)

    run_with_client(monkeypatch, cli_args, client)

    assert client.connect_calls[-1]['use_keyring'] is expected_use_keyring
    assert client.connect_calls[-1]['reset_keyring'] is False


@pytest.mark.parametrize(
    ('ssh_connection', 'expected_use_keyring'),
    (
        (None, True),
        ('client-ip client-port server-ip server-port', False),
    ),
)
def test_run_from_cli_args_uses_auto_keyring_config(
    monkeypatch: pytest.MonkeyPatch,
    ssh_connection: str | None,
    expected_use_keyring: bool,
) -> None:
    cli_args = make_cli_args()
    config = default_config()
    config['main'] = {**config['main'], 'use_keyring': 'auto'}
    client = DummyMyCli(config=config)
    if ssh_connection is None:
        monkeypatch.delenv('SSH_CONNECTION', raising=False)
    else:
        monkeypatch.setenv('SSH_CONNECTION', ssh_connection)

    run_with_client(monkeypatch, cli_args, client)

    assert client.connect_calls[-1]['use_keyring'] is expected_use_keyring
    assert client.connect_calls[-1]['reset_keyring'] is False


@pytest.mark.parametrize(
    ('flag_name', 'expected_format'),
    (
        ('csv', 'csv'),
        ('table', 'table'),
    ),
)
def test_run_from_cli_args_sets_legacy_format_flags(
    monkeypatch: pytest.MonkeyPatch,
    flag_name: str,
    expected_format: str,
) -> None:
    cli_args = make_cli_args()
    setattr(cli_args, flag_name, True)
    client = DummyMyCli()

    run_with_client(monkeypatch, cli_args, client)

    assert cli_args.format == expected_format


def test_run_from_cli_args_list_dsn_exits_with_mode_result(monkeypatch: pytest.MonkeyPatch) -> None:
    cli_args = make_cli_args()
    cli_args.list_dsn = True
    client = DummyMyCli()
    list_dsn_calls: list[DummyMyCli] = []
    monkeypatch.setattr(main, 'preprocess_cli_args', lambda args, scheme_validator: 0)

    def fake_main_list_dsn(value: DummyMyCli) -> int:
        list_dsn_calls.append(value)
        return 7

    monkeypatch.setattr(cli_runner, 'main_list_dsn', fake_main_list_dsn)

    with pytest.raises(SystemExit) as excinfo:
        cli_runner.run_from_cli_args(cli_args, lambda **_kwargs: client)

    assert excinfo.value.code == 7
    assert list_dsn_calls == [client]


def test_run_from_cli_args_maps_dsn_socket_parameter(monkeypatch: pytest.MonkeyPatch) -> None:
    cli_args = make_cli_args()
    cli_args.dsn = 'mysql://user@host/db?socket=/tmp/mysql.sock'
    client = DummyMyCli()

    run_with_client(monkeypatch, cli_args, client)

    assert client.connect_calls[-1]['socket'] == '/tmp/mysql.sock'


def test_run_from_cli_args_maps_dsn_vault_parameters(monkeypatch: pytest.MonkeyPatch) -> None:
    cli_args = make_cli_args()
    cli_args.user = 'existing-user'
    cli_args.password = 'existing-password'
    cli_args.dsn = (
        'mysql://host/db?vault_address=https%3A%2F%2Fvault.example.com&vault_mount=kv'
        '&vault_secret=database%2Fprod&vault_password_field=mysql_password'
        '&vault_username_field=mysql_username'
    )
    client = DummyMyCli()

    run_with_client(monkeypatch, cli_args, client)

    connect_call = client.connect_calls[-1]
    assert connect_call['vault_address'] == 'https://vault.example.com'
    assert connect_call['vault_mount'] == 'kv'
    assert connect_call['vault_secret'] == 'database/prod'
    assert connect_call['vault_password_field'] == 'mysql_password'
    assert connect_call['vault_username_field'] == 'mysql_username'


def test_run_from_cli_args_uses_no_ssl_for_auto_ssl_over_socket(monkeypatch: pytest.MonkeyPatch) -> None:
    cli_args = make_cli_args()
    cli_args.socket = '/tmp/mysql.sock'
    client = DummyMyCli()
    client.ssl_mode = 'auto'

    run_with_client(monkeypatch, cli_args, client)

    assert client.connect_calls[-1]['ssl'] is None


def test_run_from_cli_args_merges_scalar_global_and_alias_list_init_commands(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cli_args = make_cli_args()
    cli_args.dsn = 'prod'
    client = DummyMyCli(
        config={
            **default_config(),
            'alias_dsn': {'prod': 'mysql://u:p@h/db'},
            'init-commands': {'global': 'set global=1'},
            'alias_dsn.init-commands': {'prod': ['set alias=1', 'set alias=2']},
        }
    )

    run_with_client(monkeypatch, cli_args, client)

    assert client.connect_calls[-1]['init_command'] == 'set global=1; set alias=1; set alias=2'


def test_run_from_cli_args_execute_mode_exits_with_mode_result(monkeypatch: pytest.MonkeyPatch) -> None:
    cli_args = make_cli_args()
    cli_args.execute = 'select 1'
    client = DummyMyCli()
    execute_calls: list[tuple[DummyMyCli, main.CliArgs]] = []
    monkeypatch.setattr(main, 'preprocess_cli_args', lambda args, scheme_validator: 0)
    monkeypatch.setattr(cli_runner.sys, 'stdin', SimpleNamespace(isatty=lambda: True))
    monkeypatch.setattr(cli_runner.sys.stderr, 'isatty', lambda: False)

    def fake_main_execute_from_cli(mycli: DummyMyCli, args: main.CliArgs) -> int:
        execute_calls.append((mycli, args))
        return 11

    monkeypatch.setattr(cli_runner, 'main_execute_from_cli', fake_main_execute_from_cli)

    with pytest.raises(SystemExit) as excinfo:
        cli_runner.run_from_cli_args(cli_args, lambda **_kwargs: client)

    assert excinfo.value.code == 11
    assert execute_calls == [(client, cli_args)]
    assert client.close_called is True


def test_run_from_cli_args_batch_with_progress_exits_with_mode_result(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cli_args = make_cli_args()
    cli_args.batch = 'input.sql'
    cli_args.progress = True
    client = DummyMyCli()
    batch_calls: list[tuple[DummyMyCli, main.CliArgs]] = []
    monkeypatch.setattr(main, 'preprocess_cli_args', lambda args, scheme_validator: 0)
    monkeypatch.setattr(cli_runner.sys, 'stdin', SimpleNamespace(isatty=lambda: True))
    monkeypatch.setattr(cli_runner.sys.stderr, 'isatty', lambda: True)

    def fake_main_batch_with_progress_bar(mycli: DummyMyCli, args: main.CliArgs) -> int:
        batch_calls.append((mycli, args))
        return 12

    monkeypatch.setattr(cli_runner, 'main_batch_with_progress_bar', fake_main_batch_with_progress_bar)

    with pytest.raises(SystemExit) as excinfo:
        cli_runner.run_from_cli_args(cli_args, lambda **_kwargs: client)

    assert excinfo.value.code == 12
    assert batch_calls == [(client, cli_args)]
    assert client.close_called is True


def test_run_from_cli_args_batch_without_progress_exits_with_mode_result(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cli_args = make_cli_args()
    cli_args.batch = 'input.sql'
    client = DummyMyCli()
    batch_calls: list[tuple[DummyMyCli, main.CliArgs]] = []
    monkeypatch.setattr(main, 'preprocess_cli_args', lambda args, scheme_validator: 0)
    monkeypatch.setattr(cli_runner.sys, 'stdin', SimpleNamespace(isatty=lambda: True))
    monkeypatch.setattr(cli_runner.sys.stderr, 'isatty', lambda: False)

    def fake_main_batch_without_progress_bar(mycli: DummyMyCli, args: main.CliArgs) -> int:
        batch_calls.append((mycli, args))
        return 13

    monkeypatch.setattr(cli_runner, 'main_batch_without_progress_bar', fake_main_batch_without_progress_bar)

    with pytest.raises(SystemExit) as excinfo:
        cli_runner.run_from_cli_args(cli_args, lambda **_kwargs: client)

    assert excinfo.value.code == 13
    assert batch_calls == [(client, cli_args)]
    assert client.close_called is True


def test_run_from_cli_args_stdin_batch_exits_with_mode_result(monkeypatch: pytest.MonkeyPatch) -> None:
    cli_args = make_cli_args()
    client = DummyMyCli()
    batch_calls: list[tuple[DummyMyCli, main.CliArgs]] = []
    monkeypatch.setattr(main, 'preprocess_cli_args', lambda args, scheme_validator: 0)
    monkeypatch.setattr(cli_runner.sys, 'stdin', SimpleNamespace(isatty=lambda: False))
    monkeypatch.setattr(cli_runner.sys.stderr, 'isatty', lambda: False)

    def fake_main_batch_from_stdin(mycli: DummyMyCli, args: main.CliArgs) -> int:
        batch_calls.append((mycli, args))
        return 14

    monkeypatch.setattr(cli_runner, 'main_batch_from_stdin', fake_main_batch_from_stdin)

    with pytest.raises(SystemExit) as excinfo:
        cli_runner.run_from_cli_args(cli_args, lambda **_kwargs: client)

    assert excinfo.value.code == 14
    assert batch_calls == [(client, cli_args)]
    assert client.close_called is True
