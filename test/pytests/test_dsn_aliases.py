from collections.abc import Mapping
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from urllib.parse import parse_qsl, urlsplit

import pytest

from mycli.constants import KNOWN_DSN_QUERY_PARAMS
import mycli.packages.special.dsn_aliases as dsn_aliases_module
from mycli.packages.special.dsn_aliases import INVALID_DSN_ALIAS_ERROR, DsnAliases, is_valid_dsn_alias


class DummyConfig(dict):
    def __init__(self, initial: Mapping[str, object] | None = None) -> None:
        super().__init__(initial or {})
        self.encoding: str | None = None
        self.write_calls = 0

    def write(self) -> None:
        self.write_calls += 1


class FailingConfig(DummyConfig):
    def write(self) -> None:
        raise OSError('write failed')


def test_is_valid_dsn_alias_rejects_dash_prefix() -> None:
    assert is_valid_dsn_alias('prod') is True
    assert is_valid_dsn_alias('-prod') is False


def test_from_config_returns_instance_with_same_config() -> None:
    config = DummyConfig()

    aliases = DsnAliases.from_config(config, config_file='/tmp/myclirc')

    assert isinstance(aliases, DsnAliases)
    assert aliases.config is config
    assert aliases.config_file == '/tmp/myclirc'


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


def test_save_preserves_user_config_comments_and_excludes_merged_values(tmp_path: Path) -> None:
    config_file = tmp_path / 'myclirc'
    config_file.write_text(
        """# User introduction.
[main]
prompt = custom # Inline comment.

[alias_dsn]
# Existing alias.
existing = mysql://existing/db
# User footer.
""",
        encoding='utf-8',
    )
    merged_config = DummyConfig({
        'main': {'prompt': 'custom', 'package_default': 'do not write'},
        'alias_dsn': {'existing': 'mysql://existing/db'},
    })
    aliases = DsnAliases(merged_config, config_file=str(config_file))

    result = aliases.save('new', 'mysql://new/db')

    assert result == 'Saved: new'
    assert (
        config_file.read_text(encoding='utf-8')
        == """# User introduction.
[main]
prompt = custom# Inline comment.

[alias_dsn]
# Existing alias.
existing = mysql://existing/db
new = mysql://new/db
# User footer.
"""
    )
    assert merged_config['alias_dsn']['new'] == 'mysql://new/db'
    assert 'package_default' not in config_file.read_text(encoding='utf-8')


def test_save_reloads_user_config_before_writing(tmp_path: Path) -> None:
    config_file = tmp_path / 'myclirc'
    config_file.write_text('[alias_dsn]\nexisting = mysql://existing/db\n', encoding='utf-8')
    merged_config = DummyConfig({'alias_dsn': {'existing': 'mysql://existing/db'}})
    aliases = DsnAliases(merged_config, config_file=str(config_file))
    config_file.write_text(
        '# Added while mycli is running.\n[alias_dsn]\nexisting = mysql://existing/db\nexternal = mysql://external/db\n',
        encoding='utf-8',
    )

    aliases.save('new', 'mysql://new/db')

    contents = config_file.read_text(encoding='utf-8')
    assert contents.startswith('# Added while mycli is running.\n')
    assert 'external = mysql://external/db\n' in contents
    assert 'new = mysql://new/db\n' in contents


def test_save_overwrites_alias_without_removing_its_comment(tmp_path: Path) -> None:
    config_file = tmp_path / 'myclirc'
    config_file.write_text(
        """[alias_dsn]
# Keep this explanation.
prod = mysql://old/db
""",
        encoding='utf-8',
    )
    merged_config = DummyConfig({'alias_dsn': {'prod': 'mysql://old/db'}})

    DsnAliases(merged_config, config_file=str(config_file)).save('prod', 'mysql://new/db')

    assert (
        config_file.read_text(encoding='utf-8')
        == """[alias_dsn]
# Keep this explanation.
prod = mysql://new/db
"""
    )
    assert merged_config['alias_dsn']['prod'] == 'mysql://new/db'


def test_delete_preserves_unrelated_user_config_comments(tmp_path: Path) -> None:
    config_file = tmp_path / 'myclirc'
    config_file.write_text(
        """# User introduction.
[alias_dsn]
# Removed with the alias.
remove = mysql://remove/db
# Keep this explanation.
keep = mysql://keep/db
# User footer.
""",
        encoding='utf-8',
    )
    merged_config = DummyConfig({'alias_dsn': {'remove': 'mysql://remove/db', 'keep': 'mysql://keep/db'}})
    aliases = DsnAliases(merged_config, config_file=str(config_file))

    result = aliases.delete('remove')

    assert result == 'Deleted: remove'
    assert (
        config_file.read_text(encoding='utf-8')
        == """# User introduction.
[alias_dsn]
# Keep this explanation.
keep = mysql://keep/db
# User footer.
"""
    )
    assert merged_config['alias_dsn'] == {'keep': 'mysql://keep/db'}


def test_delete_effective_system_alias_does_not_rewrite_user_config(tmp_path: Path) -> None:
    config_file = tmp_path / 'myclirc'
    original = '# User commentary.\n[main]\nprompt = custom\n'
    config_file.write_text(original, encoding='utf-8')
    merged_config = DummyConfig({'alias_dsn': {'system': 'mysql://system/db'}})
    aliases = DsnAliases(merged_config, config_file=str(config_file))

    result = aliases.delete('system')

    assert result == 'Deleted: system'
    assert config_file.read_text(encoding='utf-8') == original
    assert merged_config['alias_dsn'] == {}


def test_invalid_alias_does_not_read_user_config(monkeypatch: pytest.MonkeyPatch) -> None:
    aliases = DsnAliases(DummyConfig(), config_file='~/.myclirc')
    monkeypatch.setattr(
        dsn_aliases_module,
        'read_config_file',
        lambda _path: pytest.fail('invalid aliases must not read the user config'),
    )

    assert aliases.save('-prod', 'mysql://prod/db') == INVALID_DSN_ALIAS_ERROR
    assert aliases.delete('-prod') == INVALID_DSN_ALIAS_ERROR


def test_save_does_not_update_runtime_config_when_user_config_cannot_be_read(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    merged_config = DummyConfig({'alias_dsn': {'existing': 'mysql://existing/db'}})
    aliases = DsnAliases(merged_config, config_file='~/.myclirc')
    monkeypatch.setattr(dsn_aliases_module, 'read_config_file', lambda _path, **kwargs: None)

    with pytest.raises(OSError, match=r"Unable to read config file '.*/\.myclirc'\."):
        aliases.save('new', 'mysql://new/db')

    assert merged_config['alias_dsn'] == {'existing': 'mysql://existing/db'}


@pytest.mark.parametrize('initial', ({}, {'alias_dsn': {'existing': 'mysql://existing/db'}}))
def test_save_restores_runtime_config_after_write_failure(initial: dict[str, object]) -> None:
    config = FailingConfig(initial)
    aliases = DsnAliases(config)

    with pytest.raises(OSError, match='write failed'):
        aliases.save('new', 'mysql://new/db')

    assert config == initial


def test_save_restores_overwritten_runtime_alias_after_write_failure() -> None:
    config = FailingConfig({'alias_dsn': {'existing': 'mysql://existing/db'}})
    aliases = DsnAliases(config)

    with pytest.raises(OSError, match='write failed'):
        aliases.save('existing', 'mysql://new/db')

    assert config['alias_dsn']['existing'] == 'mysql://existing/db'


def test_delete_restores_runtime_alias_after_write_failure() -> None:
    config = FailingConfig({'alias_dsn': {'existing': 'mysql://existing/db'}})
    aliases = DsnAliases(config)

    with pytest.raises(OSError, match='write failed'):
        aliases.delete('existing')

    assert config['alias_dsn'] == {'existing': 'mysql://existing/db'}


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
