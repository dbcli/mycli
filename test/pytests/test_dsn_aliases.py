from collections.abc import Mapping

from mycli.packages.special.dsn_aliases import DsnAliases


class DummyConfig(dict):
    def __init__(self, initial: Mapping[str, object] | None = None) -> None:
        super().__init__(initial or {})
        self.encoding: str | None = None
        self.write_calls = 0

    def write(self) -> None:
        self.write_calls += 1


def test_from_config_returns_instance_with_same_config() -> None:
    config = DummyConfig()

    aliases = DsnAliases.from_config(config)

    assert isinstance(aliases, DsnAliases)
    assert aliases.config is config


def test_list_and_get_use_alias_dsn_section() -> None:
    config = DummyConfig({
        'alias_dsn': {
            'prod': 'mysql://prod/db',
            'staging': 'mysql://staging/db',
        },
    })
    aliases = DsnAliases(config)

    assert aliases.list() == ['prod', 'staging']
    assert aliases.get('prod') == 'mysql://prod/db'
    assert aliases.get('missing') is None


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


def test_delete_removes_existing_alias_and_writes_config() -> None:
    config = DummyConfig({'alias_dsn': {'prod': 'mysql://prod/db'}})
    aliases = DsnAliases(config)

    result = aliases.delete('prod')

    assert result == 'Deleted: prod'
    assert config['alias_dsn'] == {}
    assert config.write_calls == 1


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
