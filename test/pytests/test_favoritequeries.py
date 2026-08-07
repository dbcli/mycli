from collections.abc import Mapping
import logging
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


def test_from_config_merges_shared_queries_with_configured_precedence(tmp_path: Path) -> None:
    shared_file = tmp_path / 'shared-myclirc'
    shared_file.write_text(
        """[main]
prompt = ignored

[favorite_queries]
shared = select 1
overridden = select 'shared'
""",
        encoding='utf-8',
    )
    config = DummyConfig({
        'favorite_queries': {
            'local': 'select 2',
            'overridden': "select 'local'",
        },
    })

    favorites = FavoriteQueries.from_config(config, shared_favorites_file=str(shared_file))

    assert favorites.list() == ['shared', 'overridden', 'local']
    assert favorites.get('shared') == 'select 1'
    assert favorites.get('overridden') == "select 'local'"
    assert 'main' not in config


def test_from_config_rejects_relative_shared_file(
    caplog: pytest.LogCaptureFixture,
) -> None:
    config = DummyConfig({'favorite_queries': {'local': 'select 1'}})

    with caplog.at_level(logging.WARNING, logger='mycli.packages.special.favoritequeries'):
        favorites = FavoriteQueries.from_config(config, shared_favorites_file='shared-myclirc')

    assert favorites.get('local') == 'select 1'
    assert favorites.get('shared') is None
    assert "Shared favorites file path must be absolute: 'shared-myclirc'." in caplog.text


def test_from_config_expands_user_in_shared_file_path(monkeypatch: pytest.MonkeyPatch) -> None:
    read_paths: list[str] = []
    monkeypatch.setattr(favoritequeries_module.os.path, 'expanduser', lambda path: '/expanded/shared-myclirc')
    monkeypatch.setattr(favoritequeries_module.os.path, 'isfile', lambda path: True)

    def read_config_file(path: str) -> DummyConfig:
        read_paths.append(path)
        return DummyConfig({'favorite_queries': {'shared': 'select 1'}})

    monkeypatch.setattr(favoritequeries_module, 'read_config_file', read_config_file)

    favorites = FavoriteQueries.from_config(DummyConfig(), shared_favorites_file='~/shared-myclirc')

    assert read_paths == ['/expanded/shared-myclirc']
    assert favorites.get('shared') == 'select 1'


def test_from_config_warns_and_continues_for_missing_shared_file(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    config = DummyConfig({'favorite_queries': {'local': 'select 1'}})
    missing_file = tmp_path / 'missing-myclirc'

    with caplog.at_level(logging.WARNING, logger='mycli.packages.special.favoritequeries'):
        favorites = FavoriteQueries.from_config(config, shared_favorites_file=str(missing_file))

    assert favorites.get('local') == 'select 1'
    assert f"Unable to read shared favorites file '{missing_file}'." in caplog.text


def test_from_config_continues_when_shared_file_cannot_be_read(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = DummyConfig({'favorite_queries': {'local': 'select 1'}})
    monkeypatch.setattr(favoritequeries_module.os.path, 'isfile', lambda path: True)
    monkeypatch.setattr(favoritequeries_module, 'read_config_file', lambda path: None)

    favorites = FavoriteQueries.from_config(config, shared_favorites_file='/shared-myclirc')

    assert favorites.get('local') == 'select 1'


def test_from_config_uses_successfully_parsed_shared_queries(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    shared_file = tmp_path / 'shared-myclirc'
    shared_file.write_text(
        '[favorite_queries]\nshared = select 1\n[invalid\n',
        encoding='utf-8',
    )

    with caplog.at_level(logging.WARNING, logger='mycli.config'):
        favorites = FavoriteQueries.from_config(DummyConfig(), shared_favorites_file=str(shared_file))

    assert favorites.get('shared') == 'select 1'
    assert 'Unable to parse line 3 of config file' in caplog.text


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


def test_save_shared_favorite_override_writes_only_user_config(tmp_path: Path) -> None:
    shared_file = tmp_path / 'shared-myclirc'
    shared_contents = '[favorite_queries]\nreport = select 1\n'
    shared_file.write_text(shared_contents, encoding='utf-8')
    config_file = tmp_path / 'myclirc'
    config_file.write_text('# User config.\n', encoding='utf-8')
    favorites = FavoriteQueries.from_config(
        DummyConfig(),
        str(config_file),
        str(shared_file),
    )

    favorites.save('report', 'select 2')

    assert shared_file.read_text(encoding='utf-8') == shared_contents
    assert config_file.read_text(encoding='utf-8') == '# User config.\n[favorite_queries]\nreport = select 2\n'
    assert favorites.get('report') == 'select 2'


def test_delete_shared_favorite_does_not_write_either_config_file(tmp_path: Path) -> None:
    shared_file = tmp_path / 'shared-myclirc'
    shared_contents = '[favorite_queries]\nreport = select 1\n'
    shared_file.write_text(shared_contents, encoding='utf-8')
    config_file = tmp_path / 'myclirc'
    user_contents = '# User config.\n'
    config_file.write_text(user_contents, encoding='utf-8')
    favorites = FavoriteQueries.from_config(
        DummyConfig(),
        str(config_file),
        str(shared_file),
    )

    result = favorites.delete('report')

    assert result == 'report: Deleted.'
    assert favorites.get('report') is None
    assert shared_file.read_text(encoding='utf-8') == shared_contents
    assert config_file.read_text(encoding='utf-8') == user_contents


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
