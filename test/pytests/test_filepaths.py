import importlib.util
import os
from pathlib import Path
import platform
import sys
from types import ModuleType
from typing import Any

import pytest

from mycli.packages import filepaths


def load_filepaths_variant(
    monkeypatch: pytest.MonkeyPatch,
    *,
    os_name: str,
    system_name: str,
) -> ModuleType:
    module_path = str(Path(filepaths.__file__).resolve())
    monkeypatch.setattr(os, 'name', os_name, raising=False)
    monkeypatch.setattr(platform, 'system', lambda: system_name)
    module_name = f'filepaths_variant_{os_name}_{system_name}'
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def test_default_socket_dirs_import_variants(monkeypatch: pytest.MonkeyPatch) -> None:
    darwin = load_filepaths_variant(monkeypatch, os_name='posix', system_name='Darwin')
    assert darwin.DEFAULT_SOCKET_DIRS == ['/tmp']

    linux = load_filepaths_variant(monkeypatch, os_name='posix', system_name='Linux')
    assert linux.DEFAULT_SOCKET_DIRS == ['/var/run', '/var/lib']

    windows = load_filepaths_variant(monkeypatch, os_name='nt', system_name='Windows')
    assert windows.DEFAULT_SOCKET_DIRS == []


def test_list_path_lists_sql_files_and_directories(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / '.hidden.sql').write_text('select 1\n', encoding='utf-8')
    (tmp_path / 'visible.SQL').write_text('select 1\n', encoding='utf-8')
    (tmp_path / 'notes.txt').write_text('ignored\n', encoding='utf-8')
    (tmp_path / 'folder').mkdir()

    assert filepaths.list_path(str(tmp_path)) == ['visible.SQL', 'folder/']
    assert filepaths.list_path(str(tmp_path / 'missing')) == []


def test_complete_path_and_parse_path() -> None:
    assert filepaths.complete_path('abc', '') == 'abc'
    assert filepaths.complete_path('abcdef', 'abc') == 'abcdef'
    assert filepaths.complete_path('docs', '~') == os.path.join('~', 'docs')
    assert filepaths.complete_path('docs', 'other') == ''

    assert filepaths.parse_path('') == ('', '', 0)
    assert filepaths.parse_path('/tmp/query.sql') == ('/tmp', 'query.sql', -9)
    assert filepaths.parse_path('/tmp/dir/') == ('/tmp/dir', '', 0)


def test_suggest_path_branches(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / 'query.sql').write_text('select 1\n', encoding='utf-8')
    (tmp_path / 'subdir').mkdir()

    assert filepaths.suggest_path('') == [
        os.path.abspath(os.sep),
        '~',
        os.curdir,
        os.pardir,
        'query.sql',
        'subdir/',
    ]

    assert filepaths.suggest_path('relative') == ['query.sql', 'subdir/']

    home = tmp_path / 'home'
    home.mkdir()
    (home / 'from_home.sql').write_text('select 1\n', encoding='utf-8')
    monkeypatch.setattr(os.path, 'expanduser', lambda path: str(home))
    assert filepaths.suggest_path('~/f') == ['from_home.sql']

    nested = tmp_path / 'nested'
    nested.mkdir()
    (nested / 'inside.sql').write_text('select 1\n', encoding='utf-8')
    assert filepaths.suggest_path(str(nested / 'missing.sql')) == ['inside.sql']


def test_dir_path_exists(tmp_path: Path) -> None:
    existing = tmp_path / 'logs' / 'mycli.log'
    existing.parent.mkdir()
    assert filepaths.dir_path_exists(str(existing)) is True
    assert filepaths.dir_path_exists(str(tmp_path / 'missing' / 'mycli.log')) is False


def test_guess_socket_location_returns_matching_socket(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(filepaths, 'DEFAULT_SOCKET_DIRS', ['/a', '/b'])
    monkeypatch.setattr(filepaths.os.path, 'exists', lambda path: path == '/b')
    monkeypatch.setattr(
        filepaths.os,
        'walk',
        lambda directory, topdown=True: iter([
            ('/b', ['mysql-data', 'other'], ['mysqlx.sock', 'mysql.socket']),
        ]),
    )
    assert filepaths.guess_socket_location() == '/b/mysql.socket'


def test_guess_socket_location_prunes_dirs_and_returns_none(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(filepaths, 'DEFAULT_SOCKET_DIRS', ['/a'])
    monkeypatch.setattr(filepaths.os.path, 'exists', lambda path: True)
    walked_dirs: list[list[str]] = []

    def fake_walk(directory: str, topdown: bool = True) -> Any:
        dirs = ['mysql-data', 'tmp', 'mysqlx', 'other']
        walked_dirs.append(dirs)
        yield (directory, dirs, ['mysqlx.sock', 'readme.txt'])

    monkeypatch.setattr(filepaths.os, 'walk', fake_walk)
    assert filepaths.guess_socket_location() is None
    assert walked_dirs[0] == ['mysql-data', 'mysqlx']
