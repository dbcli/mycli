from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from mycli import cli_runner, main


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
        self.connect_calls: list[dict[str, Any]] = []
        self.run_cli_called = False
        self.close_called = False

    def connect(self, **kwargs: Any) -> None:
        self.connect_calls.append(dict(kwargs))

    def run_cli(self) -> None:
        self.run_cli_called = True

    def close(self) -> None:
        self.close_called = True


def default_config() -> dict[str, Any]:
    return {
        'main': {'use_keyring': 'false'},
        'connection': {'default_keepalive_ticks': 0},
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
    assert connect_call['passwd'] == 'p'
    assert connect_call['host'] == 'h'
    assert connect_call['database'] == 'db'


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
    assert client.connect_calls[-1]['passwd'] == 'env_pass'
    assert client.connect_calls[-1]['host'] == 'env-host'
    assert client.connect_calls[-1]['port'] == 3308
    assert client.connect_calls[-1]['database'] == 'env_db'
    assert client.connect_calls[-1]['character_set'] == 'utf8mb4'
    assert client.connect_calls[-1]['keepalive_ticks'] == 9


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


def test_run_from_cli_args_maps_dsn_ssl_parameters(monkeypatch: pytest.MonkeyPatch) -> None:
    cli_args = make_cli_args()
    cli_args.dsn = (
        'mysql://user:pass@host:3306/db?ssl=true&ssl_ca=~/ca.pem&ssl_capath=/capath'
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
    assert any('"ssl" DSN URI parameter is deprecated' in call for call in secho_calls)


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
