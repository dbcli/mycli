from collections.abc import Mapping
from pathlib import Path

import pytest

import mycli.packages.special.favoritequeries as favoritequeries_module
from mycli.packages.special.favoritequeries import FavoriteQueries


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


def test_from_config_returns_instance_with_same_config() -> None:
    config = DummyConfig()

    favorites = FavoriteQueries.from_config(config, '/tmp/myclirc')

    assert isinstance(favorites, FavoriteQueries)
    assert favorites.config is config
    assert favorites.config_file == '/tmp/myclirc'


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


def test_save_preserves_user_config_comments_and_excludes_merged_values(tmp_path: Path) -> None:
    config_file = tmp_path / 'myclirc'
    config_file.write_text(
        """# User introduction.
[main]
prompt = custom # Inline comment.

[favorite_queries]
# Existing favorite.
existing = select 1
# User footer.
""",
        encoding='utf-8',
    )
    merged_config = DummyConfig({
        'main': {'prompt': 'custom', 'package_default': 'do not write'},
        'favorite_queries': {'existing': 'select 1'},
    })
    favorites = FavoriteQueries(merged_config, str(config_file))

    favorites.save('new', 'select 2')

    assert (
        config_file.read_text(encoding='utf-8')
        == """# User introduction.
[main]
prompt = custom# Inline comment.

[favorite_queries]
# Existing favorite.
existing = select 1
new = select 2
# User footer.
"""
    )
    assert merged_config['favorite_queries']['new'] == 'select 2'
    assert 'package_default' not in config_file.read_text(encoding='utf-8')


def test_save_overwrites_favorite_without_removing_its_comment(tmp_path: Path) -> None:
    config_file = tmp_path / 'myclirc'
    config_file.write_text(
        """[favorite_queries]
# Keep this explanation.
report = select 1
""",
        encoding='utf-8',
    )
    merged_config = DummyConfig({'favorite_queries': {'report': 'select 1'}})

    FavoriteQueries(merged_config, str(config_file)).save('report', 'select 2')

    assert (
        config_file.read_text(encoding='utf-8')
        == """[favorite_queries]
# Keep this explanation.
report = select 2
"""
    )
    assert merged_config['favorite_queries']['report'] == 'select 2'


def test_delete_preserves_unrelated_user_config_comments(tmp_path: Path) -> None:
    config_file = tmp_path / 'myclirc'
    config_file.write_text(
        """# User introduction.
[favorite_queries]
# Removed with the favorite.
remove = select 1
# Keep this explanation.
keep = select 2
# User footer.
""",
        encoding='utf-8',
    )
    merged_config = DummyConfig({'favorite_queries': {'remove': 'select 1', 'keep': 'select 2'}})
    favorites = FavoriteQueries(merged_config, str(config_file))

    result = favorites.delete('remove')

    assert result == 'remove: Deleted.'
    assert (
        config_file.read_text(encoding='utf-8')
        == """# User introduction.
[favorite_queries]
# Keep this explanation.
keep = select 2
# User footer.
"""
    )
    assert merged_config['favorite_queries'] == {'keep': 'select 2'}


def test_delete_effective_system_favorite_does_not_rewrite_user_config(tmp_path: Path) -> None:
    config_file = tmp_path / 'myclirc'
    original = '# User commentary.\n[main]\nprompt = custom\n'
    config_file.write_text(original, encoding='utf-8')
    merged_config = DummyConfig({'favorite_queries': {'system': 'select 1'}})
    favorites = FavoriteQueries(merged_config, str(config_file))

    result = favorites.delete('system')

    assert result == 'system: Deleted.'
    assert config_file.read_text(encoding='utf-8') == original
    assert merged_config['favorite_queries'] == {}


def test_save_does_not_update_runtime_config_when_user_config_cannot_be_read(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    merged_config = DummyConfig({'favorite_queries': {'existing': 'select 1'}})
    favorites = FavoriteQueries(merged_config, '~/.myclirc')
    monkeypatch.setattr(favoritequeries_module, 'read_config_file', lambda _path, **_kwargs: None)

    with pytest.raises(OSError, match=r"Unable to read config file '.*/\.myclirc'\."):
        favorites.save('new', 'select 2')

    assert merged_config['favorite_queries'] == {'existing': 'select 1'}


@pytest.mark.parametrize('initial', ({}, {'favorite_queries': {'existing': 'select 1'}}))
def test_save_restores_runtime_config_after_write_failure(initial: dict[str, object]) -> None:
    config = FailingConfig(initial)
    favorites = FavoriteQueries(config)

    with pytest.raises(OSError, match='write failed'):
        favorites.save('new', 'select 2')

    assert config == initial


def test_save_restores_overwritten_runtime_query_after_write_failure() -> None:
    config = FailingConfig({'favorite_queries': {'existing': 'select 1'}})
    favorites = FavoriteQueries(config)

    with pytest.raises(OSError, match='write failed'):
        favorites.save('existing', 'select 2')

    assert config['favorite_queries']['existing'] == 'select 1'


def test_delete_restores_runtime_query_after_write_failure() -> None:
    config = FailingConfig({'favorite_queries': {'existing': 'select 1'}})
    favorites = FavoriteQueries(config)

    with pytest.raises(OSError, match='write failed'):
        favorites.delete('existing')

    assert config['favorite_queries'] == {'existing': 'select 1'}
