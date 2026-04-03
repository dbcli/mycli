from collections.abc import Mapping

from mycli.packages.special.favoritequeries import FavoriteQueries


class DummyConfig(dict):
    def __init__(self, initial: Mapping[str, object] | None = None) -> None:
        super().__init__(initial or {})
        self.encoding: str | None = None
        self.write_calls = 0

    def write(self) -> None:
        self.write_calls += 1


def test_from_config_returns_instance_with_same_config() -> None:
    config = DummyConfig()

    favorites = FavoriteQueries.from_config(config)

    assert isinstance(favorites, FavoriteQueries)
    assert favorites.config is config


def test_list_and_get_use_favorite_queries_section() -> None:
    config = DummyConfig({
        'favorite_queries': {
            'daily': 'select 1',
            'weekly': 'select 2',
        },
    })
    favorites = FavoriteQueries(config)

    assert favorites.list() == ['daily', 'weekly']
    assert favorites.get('daily') == 'select 1'
    assert favorites.get('missing') is None


def test_list_returns_empty_list_when_section_is_missing() -> None:
    favorites = FavoriteQueries(DummyConfig())

    assert favorites.list() == []


def test_save_creates_section_sets_encoding_and_writes_config() -> None:
    config = DummyConfig()
    favorites = FavoriteQueries(config)

    favorites.save('demo', 'select 1')

    assert config.encoding == 'utf-8'
    assert config == {'favorite_queries': {'demo': 'select 1'}}
    assert config.write_calls == 1


def test_save_updates_existing_section_and_writes_config() -> None:
    config = DummyConfig({'favorite_queries': {'demo': 'select 1'}})
    favorites = FavoriteQueries(config)

    favorites.save('report', 'select 2')

    assert config.encoding == 'utf-8'
    assert config['favorite_queries'] == {
        'demo': 'select 1',
        'report': 'select 2',
    }
    assert config.write_calls == 1


def test_delete_removes_existing_favorite_and_writes_config() -> None:
    config = DummyConfig({'favorite_queries': {'demo': 'select 1'}})
    favorites = FavoriteQueries(config)

    result = favorites.delete('demo')

    assert result == 'demo: Deleted.'
    assert config['favorite_queries'] == {}
    assert config.write_calls == 1


def test_delete_returns_not_found_without_writing_config() -> None:
    config = DummyConfig({'favorite_queries': {'demo': 'select 1'}})
    favorites = FavoriteQueries(config)

    result = favorites.delete('missing')

    assert result == 'missing: Not Found.'
    assert config['favorite_queries'] == {'demo': 'select 1'}
    assert config.write_calls == 0


def test_delete_returns_not_found_when_section_is_missing() -> None:
    config = DummyConfig()
    favorites = FavoriteQueries(config)

    result = favorites.delete('missing')

    assert result == 'missing: Not Found.'
    assert config == {}
    assert config.write_calls == 0
