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


@pytest.mark.skipif(os.name == 'nt', reason='todo: unknown')
def test_default_socket_dirs_import_variants(monkeypatch: pytest.MonkeyPatch) -> None:
    darwin = load_filepaths_variant(monkeypatch, os_name='posix', system_name='Darwin')
    assert darwin.DEFAULT_SOCKET_DIRS == ['/tmp']

    linux = load_filepaths_variant(monkeypatch, os_name='posix', system_name='Linux')
    assert linux.DEFAULT_SOCKET_DIRS == ['/var/run', '/var/lib']

    windows = load_filepaths_variant(monkeypatch, os_name='nt', system_name='Windows')
    assert windows.DEFAULT_SOCKET_DIRS == []


def test_list_path_lists_sql_files_and_directories(tmp_path: Path) -> None:
    (tmp_path / '.hidden.sql').write_text('select 1\n', encoding='utf-8')
    (tmp_path / 'visible.SQL').write_text('select 1\n', encoding='utf-8')
    (tmp_path / 'notes.txt').write_text('ignored\n', encoding='utf-8')
    (tmp_path / 'output').write_text('ignored\n', encoding='utf-8')
    (tmp_path / 'folder').mkdir()

    assert filepaths.list_path(str(tmp_path)) == ['visible.SQL', 'folder/']
    assert filepaths.list_path(str(tmp_path), sql_only=False) == [
        'notes.txt',
        'output',
        'visible.SQL',
        'folder/',
    ]
    assert filepaths.list_path(str(tmp_path / 'missing')) == []


def test_complete_path_and_parse_path() -> None:
    assert filepaths.complete_path('abc', '') == 'abc'
    assert filepaths.complete_path('abcdef', 'abc') == 'abcdef'
    assert filepaths.complete_path('docs', '~') == os.path.join('~', 'docs')
    assert filepaths.complete_path('docs', 'other') == ''

    assert filepaths.parse_path('') == ('', '', 0)
    assert filepaths.parse_path('/tmp/query.sql') == ('/tmp', 'query.sql', -9)
    assert filepaths.parse_path('/tmp/dir/') == ('/tmp/dir', '', 0)


@pytest.mark.skipif(os.name == 'nt', reason='todo: unknown')
def test_suggest_path_branches(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / 'query.sql').write_text('select 1\n', encoding='utf-8')
    (tmp_path / 'report.csv').write_text('result\n', encoding='utf-8')
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
    assert filepaths.suggest_path('relative', sql_only=False) == ['query.sql', 'report.csv', 'subdir/']

    home = tmp_path / 'home'
    home.mkdir()
    (home / 'from_home.sql').write_text('select 1\n', encoding='utf-8')
    monkeypatch.setattr(os.path, 'expanduser', lambda path: str(home))
    assert filepaths.suggest_path('~/f') == ['from_home.sql']

    nested = tmp_path / 'nested'
    nested.mkdir()
    (nested / 'inside.sql').write_text('select 1\n', encoding='utf-8')
    (nested / 'child').mkdir()
    assert filepaths.suggest_path(str(nested / 'missing.sql')) == ['inside.sql', 'child/']
    assert filepaths.suggest_path('./nested/missing.sql') == ['inside.sql', 'child/']
    assert filepaths.suggest_path('nested/') == ['inside.sql', 'child/']


def test_suggest_path_by_prefix_completes_each_component(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    nested = tmp_path / 'directory' / 'subdirectory'
    nested.mkdir(parents=True)
    (nested / 'example.sql').touch()
    (nested / 'example.csv').touch()

    assert filepaths.suggest_path_by_prefix('./dir/sub/exa') == [
        './directory/subdirectory/example.sql',
    ]
    assert filepaths.suggest_path_by_prefix('./dir/sub/exa', sql_only=False) == [
        './directory/subdirectory/example.csv',
        './directory/subdirectory/example.sql',
    ]
    assert filepaths.suggest_path_by_prefix('./missing/sub/exa') == []


def test_suggest_path_by_prefix_returns_ambiguous_directories(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / 'directory').mkdir()
    (tmp_path / 'dirt').mkdir()

    assert filepaths.suggest_path_by_prefix('./dir') == ['./directory/', './dirt/']


def test_suggest_path_by_prefix_preserves_path_anchors(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    nested = tmp_path / 'directory' / 'subdirectory'
    nested.mkdir(parents=True)
    (nested / 'example.sql').touch()

    absolute_prefix = f'{tmp_path}/dir/sub/exa'
    assert filepaths.suggest_path_by_prefix(absolute_prefix) == [
        f'{tmp_path}/directory/subdirectory/example.sql',
    ]

    home = tmp_path / 'home'
    home_nested = home / 'directory' / 'subdirectory'
    home_nested.mkdir(parents=True)
    (home_nested / 'example.sql').touch()
    monkeypatch.setattr(os.path, 'expanduser', lambda path: str(home) if path == '~' else path)
    assert filepaths.suggest_path_by_prefix('~/dir/sub/exa') == [
        '~/directory/subdirectory/example.sql',
    ]

    child = tmp_path / 'child'
    child.mkdir()
    monkeypatch.chdir(child)
    assert filepaths.suggest_path_by_prefix('../dir/sub/exa') == [
        '../directory/subdirectory/example.sql',
    ]
    assert filepaths.suggest_path_by_prefix('../dir//sub/exa') == [
        '../directory/subdirectory/example.sql',
    ]


def test_suggest_path_by_prefix_preserves_windows_drive(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(os.path, 'splitdrive', lambda path: ('C:', '/dir'))
    monkeypatch.setattr(
        filepaths,
        'list_path',
        lambda root_dir, *, sql_only: ['directory/'] if root_dir == f'C:{os.sep}' else [],
    )

    assert filepaths.suggest_path_by_prefix('C:/dir') == ['C:/directory/']


def test_dir_path_exists(tmp_path: Path) -> None:
    existing = tmp_path / 'logs' / 'mycli.log'
    existing.parent.mkdir()
    assert filepaths.dir_path_exists(str(existing)) is True
    assert filepaths.dir_path_exists(str(tmp_path / 'missing' / 'mycli.log')) is False


@pytest.mark.skipif(os.name == 'nt', reason='todo: unknown')
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
