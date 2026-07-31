from collections.abc import Mapping
from types import SimpleNamespace
from typing import Any
from urllib.parse import parse_qsl, urlsplit

from mycli.constants import KNOWN_DSN_QUERY_PARAMS
from mycli.packages.special.dsn_aliases import INVALID_DSN_ALIAS_ERROR, DsnAliases, is_valid_dsn_alias


class DummyConfig(dict):
    def __init__(self, initial: Mapping[str, object] | None = None) -> None:
        super().__init__(initial or {})
        self.encoding: str | None = None
        self.write_calls = 0

    def write(self) -> None:
        self.write_calls += 1


def test_is_valid_dsn_alias_rejects_dash_prefix() -> None:
    assert is_valid_dsn_alias('prod') is True
    assert is_valid_dsn_alias('-prod') is False


def test_from_config_returns_instance_with_same_config() -> None:
    config = DummyConfig()

    aliases = DsnAliases.from_config(config)

    assert isinstance(aliases, DsnAliases)
    assert aliases.config is config


def test_from_config_retains_mycli_runtime() -> None:
    config = DummyConfig()
    mycli: Any = SimpleNamespace()

    aliases = DsnAliases.from_config(config, mycli)  # type: ignore[arg-type]

    assert aliases.mycli is mycli


def test_query_param_defaults_without_runtime_returns_empty_dict() -> None:
    aliases = DsnAliases(DummyConfig())

    assert aliases._query_param_defaults() == {}


def test_query_param_defaults_treats_invalid_boolean_as_false() -> None:
    config = DummyConfig({
        'connection': {'default_ssl_verify_server_cert': 'invalid'},
    })
    mycli = SimpleNamespace(default_keepalive_ticks=30, ssl_mode='auto')
    aliases = DsnAliases(config, mycli)  # type: ignore[arg-type]

    assert aliases._query_param_defaults()['ssl_verify_server_cert'] is False


def test_list_and_get_use_alias_dsn_section() -> None:
    config = DummyConfig({
        'alias_dsn': {
            'prod': 'mysql://prod/db',
            'staging': 'mysql://staging/db',
            '-hidden': 'mysql://hidden/db',
        },
    })
    aliases = DsnAliases(config)

    assert aliases.list() == ['prod', 'staging']
    assert aliases.get('prod') == 'mysql://prod/db'
    assert aliases.get('missing') is None
    assert aliases.get('-hidden') is None


def test_list_returns_empty_list_when_section_is_missing() -> None:
    aliases = DsnAliases(DummyConfig())

    assert aliases.list() == []


def test_save_creates_section_sets_encoding_and_writes_config() -> None:
    config = DummyConfig()
    aliases = DsnAliases(config)

    result = aliases.save('prod', 'mysql://prod/db')

    assert result == 'Saved: prod'
    assert config.encoding == 'utf-8'
    assert config == {'alias_dsn': {'prod': 'mysql://prod/db'}}
    assert config.write_calls == 1


def test_save_updates_existing_section_and_writes_config() -> None:
    config = DummyConfig({'alias_dsn': {'prod': 'mysql://prod/db'}})
    aliases = DsnAliases(config)

    result = aliases.save('staging', 'mysql://staging/db')

    assert result == 'Saved: staging'
    assert config.encoding == 'utf-8'
    assert config['alias_dsn'] == {
        'prod': 'mysql://prod/db',
        'staging': 'mysql://staging/db',
    }
    assert config.write_calls == 1


def test_save_rejects_dash_prefixed_alias_without_writing_config() -> None:
    config = DummyConfig()
    aliases = DsnAliases(config)

    result = aliases.save('-prod', 'mysql://prod/db')

    assert result == INVALID_DSN_ALIAS_ERROR
    assert config.encoding is None
    assert config == {}
    assert config.write_calls == 0


def test_delete_removes_existing_alias_and_writes_config() -> None:
    config = DummyConfig({'alias_dsn': {'prod': 'mysql://prod/db'}})
    aliases = DsnAliases(config)

    result = aliases.delete('prod')

    assert result == 'Deleted: prod'
    assert config['alias_dsn'] == {}
    assert config.write_calls == 1


def test_delete_rejects_dash_prefixed_alias_without_writing_config() -> None:
    config = DummyConfig({'alias_dsn': {'-prod': 'mysql://prod/db'}})
    aliases = DsnAliases(config)

    result = aliases.delete('-prod')

    assert result == INVALID_DSN_ALIAS_ERROR
    assert config['alias_dsn'] == {'-prod': 'mysql://prod/db'}
    assert config.write_calls == 0


def test_delete_returns_not_found_without_writing_config() -> None:
    config = DummyConfig({'alias_dsn': {'prod': 'mysql://prod/db'}})
    aliases = DsnAliases(config)

    result = aliases.delete('missing')

    assert result == 'Not Found: missing'
    assert config['alias_dsn'] == {'prod': 'mysql://prod/db'}
    assert config.write_calls == 0


def test_delete_returns_not_found_when_section_is_missing() -> None:
    config = DummyConfig()
    aliases = DsnAliases(config)

    result = aliases.delete('missing')

    assert result == 'Not Found: missing'
    assert config == {}
    assert config.write_calls == 0


def test_dsn_more_adds_non_default_runtime_parameters_in_sorted_order() -> None:
    config = DummyConfig({
        'main': {'prompt': 'configured> '},
        'connection': {
            'default_character_set': 'latin1',
            'default_keepalive_ticks': '30',
            'default_socket': '/default.sock',
            'default_ssl_mode': 'auto',
            'default_ssl_ca': '/default-ca.pem',
            'default_ssl_verify_server_cert': 'False',
        },
        'vault_beta': {
            'address': 'https://default-vault',
            'default_mount': 'kv',
            'default_password_field': 'password',
            'default_username_field': 'username',
        },
    })
    mycli = SimpleNamespace(
        default_keepalive_ticks=30,
        keepalive_ticks=45,
        prompt_format='runtime> ',
        ssl_mode='auto',
        sqlexecute=SimpleNamespace(
            character_set='utf8',
            ssl={
                'mode': 'on',
                'ca': '/runtime-ca.pem',
                'capath': '/runtime-ca',
                'cert': '/client-cert.pem',
                'cipher': 'AES256',
                'key': '/client-key.pem',
                'check_hostname': True,
                'tls_version': 'TLSv1.3',
            },
        ),
    )
    aliases = DsnAliases(config, mycli)  # type: ignore[arg-type]
    dsn = (
        'mysql://user@host/db?socket=%2Fruntime.sock&ssh_jump=bastion'
        '&vault_address=https%3A%2F%2Fruntime-vault&vault_mount=runtime-kv'
        '&vault_secret=database%2Fprod&vault_password_field=secret&vault_username_field=login'
    )

    more_dsn = aliases.dsn_more(dsn)

    parsed = urlsplit(more_dsn)
    assert (parsed.scheme, parsed.netloc, parsed.path) == ('mysql', 'user@host', '/db')
    more_params = parse_qsl(parsed.query)
    assert {key for key, _value in more_params} == KNOWN_DSN_QUERY_PARAMS
    assert more_params == [
        ('character_set', 'utf8'),
        ('keepalive_ticks', '45'),
        ('prompt', 'runtime> '),
        ('socket', '/runtime.sock'),
        ('ssh_jump', 'bastion'),
        ('ssl_ca', '/runtime-ca.pem'),
        ('ssl_capath', '/runtime-ca'),
        ('ssl_cert', '/client-cert.pem'),
        ('ssl_cipher', 'AES256'),
        ('ssl_key', '/client-key.pem'),
        ('ssl_mode', 'on'),
        ('ssl_verify_server_cert', 'true'),
        ('tls_version', 'TLSv1.3'),
        ('vault_address', 'https://runtime-vault'),
        ('vault_mount', 'runtime-kv'),
        ('vault_password_field', 'secret'),
        ('vault_secret', 'database/prod'),
        ('vault_username_field', 'login'),
    ]


def test_dsn_more_omits_empty_false_and_active_default_parameters() -> None:
    config = DummyConfig({
        'main': {'prompt': 'configured> '},
        'connection': {
            'default_character_set': 'latin1',
            'default_socket': '/default.sock',
            'default_ssl_ca': '/default-ca.pem',
            'default_ssl_mode': 'on',
            'default_ssl_verify_server_cert': 'True',
        },
        'vault_beta': {
            'address': 'https://default-vault',
            'default_mount': 'kv',
            'default_password_field': 'secret',
            'default_username_field': 'login',
        },
    })
    mycli = SimpleNamespace(
        default_keepalive_ticks=30,
        keepalive_ticks=30,
        prompt_format='configured> ',
        ssl_mode='on',
        sqlexecute=SimpleNamespace(
            character_set='latin1',
            ssl={'mode': 'on', 'ca': '/default-ca.pem', 'check_hostname': True},
        ),
    )
    aliases = DsnAliases(config, mycli)  # type: ignore[arg-type]
    dsn = (
        'mysql://user@host/db?socket=%2Fdefault.sock&vault_address=https%3A%2F%2Fdefault-vault'
        '&vault_mount=kv&vault_password_field=secret&vault_username_field=login&vault_secret='
    )

    assert aliases.dsn_more(dsn) == 'mysql://user@host/db'


def test_dsn_more_without_runtime_returns_original_dsn() -> None:
    aliases = DsnAliases(DummyConfig())

    assert aliases.dsn_more('mysql://user@host/db?socket=%2Ftmp%2Fmysql.sock') == ('mysql://user@host/db?socket=%2Ftmp%2Fmysql.sock')


def test_dsn_more_without_sql_executor_returns_original_dsn() -> None:
    mycli = SimpleNamespace(sqlexecute=None)
    aliases = DsnAliases(DummyConfig(), mycli)  # type: ignore[arg-type]
    dsn = 'mysql://user@host/db?socket=%2Ftmp%2Fmysql.sock'

    assert aliases.dsn_more(dsn) == dsn
