from __future__ import annotations

import logging
import os
from pathlib import Path
import subprocess
import sys
from typing import Any, cast

from click.testing import CliRunner
import pytest

from mycli import cli_runner, main
from mycli import client as client_module
from mycli import config as config_module
from mycli.main_modes import list_dsn as list_dsn_mode
from mycli.packages.utils import dsn_utils


class DummyConfig:
    def __init__(self, value: dict[str, str] | Exception) -> None:
        self.value = value

    def __getitem__(self, key: str) -> dict[str, str]:
        assert key == 'alias_dsn'
        if isinstance(self.value, Exception):
            raise self.value
        return self.value


def main_list_dsn(config: DummyConfig, verbosity: int = 0) -> int:
    return list_dsn_mode.main_list_dsn(cast(Any, config), verbosity)


def test_main_list_dsn_lists_aliases_without_values(monkeypatch) -> None:
    secho_calls: list[tuple[str, bool | None, str | None]] = []
    config = DummyConfig({
        'prod': 'mysql://u:p@h/db',
        '-hidden': 'mysql://hidden/db',
        'staging': 'mysql://u2:p2@h2/db2',
    })

    monkeypatch.setattr(
        list_dsn_mode.click,
        'secho',
        lambda message, err=None, fg=None: secho_calls.append((message, err, fg)),
    )

    result = main_list_dsn(config)

    assert result == 0
    assert secho_calls == [
        ('prod', None, None),
        ('staging', None, None),
    ]


def test_main_list_dsn_lists_aliases_with_values_in_verbose_mode(monkeypatch) -> None:
    secho_calls: list[tuple[str, bool | None, str | None]] = []
    config = DummyConfig({'prod': 'mysql://u:p@h/db', '-hidden': 'mysql://hidden/db'})

    monkeypatch.setattr(
        list_dsn_mode.click,
        'secho',
        lambda message, err=None, fg=None: secho_calls.append((message, err, fg)),
    )

    result = main_list_dsn(config, 1)

    assert result == 0
    assert secho_calls == [('prod : mysql://u:p@h/db', None, None)]


def test_main_list_dsn_reports_invalid_alias_section(monkeypatch) -> None:
    secho_calls: list[tuple[str, bool | None, str | None]] = []
    config = DummyConfig(KeyError('alias_dsn'))

    monkeypatch.setattr(
        list_dsn_mode.click,
        'secho',
        lambda message, err=None, fg=None: secho_calls.append((message, err, fg)),
    )

    result = main_list_dsn(config)

    assert result == 1
    assert secho_calls == [
        (
            'Invalid DSNs found in the config file. Please check the "[alias_dsn]" section in myclirc.',
            True,
            'red',
        )
    ]


def test_main_list_dsn_reports_other_config_errors(monkeypatch) -> None:
    secho_calls: list[tuple[str, bool | None, str | None]] = []
    config = DummyConfig(RuntimeError('boom'))

    monkeypatch.setattr(
        list_dsn_mode.click,
        'secho',
        lambda message, err=None, fg=None: secho_calls.append((message, err, fg)),
    )

    result = main_list_dsn(config)

    assert result == 1
    assert secho_calls == [('boom', True, 'red')]


@pytest.fixture(autouse=True)
def isolated_config(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(config_module, 'SYSTEM_CONFIG_FILES', [])
    # Reproduce startup logging before another test configures the client.
    monkeypatch.setattr(config_module.logger, 'parent', logging.getLogger())
    monkeypatch.setattr(dsn_utils.logger, 'parent', logging.getLogger())
    monkeypatch.setenv('HOME', str(tmp_path))
    monkeypatch.setenv('USERPROFILE', str(tmp_path))
    monkeypatch.setenv('XDG_CONFIG_HOME', str(tmp_path / 'xdg'))


@pytest.mark.parametrize('location', ['explicit', 'xdg', 'home'])
def test_list_dsn_selects_user_config(location: str, tmp_path: Path) -> None:
    home = tmp_path / '.myclirc'
    home.write_text('[alias_dsn]\nhome = mysql://home/db\n')
    args = ['--list-dsn']
    if location in ('explicit', 'xdg'):
        xdg = tmp_path / 'xdg' / 'mycli' / 'myclirc'
        xdg.parent.mkdir(parents=True)
        xdg.write_text('[alias_dsn]\nxdg = mysql://xdg/db\n')
    if location == 'explicit':
        explicit = tmp_path / 'explicit'
        explicit.write_text('[alias_dsn]\nexplicit = mysql://explicit/db\n')
        args += ['--myclirc', str(explicit)]

    result = CliRunner().invoke(main.click_entrypoint, args)

    assert result.exit_code == 0
    assert result.output == f'{location}\n'


def test_list_dsn_merges_system_user_and_shared_aliases(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    shared = tmp_path / 'shared'
    shared.write_text('[alias_dsn]\nshared = mysql://shared/db\noverridden = mysql://shared/db\n')
    system = tmp_path / 'system'
    system.write_text(f'[main]\nshared_dsns_file = {shared}\n[alias_dsn]\nsystem = mysql://system/db\noverridden = mysql://system/db\n')
    user = tmp_path / '.myclirc'
    user.write_text('[alias_dsn]\nuser = mysql://user/db\noverridden = mysql://user/db\n')
    monkeypatch.setattr(config_module, 'SYSTEM_CONFIG_FILES', [str(system)])

    result = CliRunner().invoke(main.click_entrypoint, ['--list-dsn', '--verbose'])

    assert result.exit_code == 0
    assert result.output == 'shared : mysql://shared/db\noverridden : mysql://user/db\nsystem : mysql://system/db\nuser : mysql://user/db\n'


@pytest.mark.parametrize('explicit', [False, True])
def test_list_dsn_does_not_create_missing_config(tmp_path: Path, explicit: bool) -> None:
    path = tmp_path / '.myclirc'
    args = ['--list-dsn'] + (['--myclirc', str(path)] if explicit else [])

    result = CliRunner().invoke(main.click_entrypoint, args)

    assert result.exit_code == 0
    assert result.output == ''
    assert not path.exists()


@pytest.mark.parametrize('existing', [False, True])
def test_list_dsn_does_not_touch_configured_logs(tmp_path: Path, existing: bool) -> None:
    log = tmp_path / 'debug.log'
    audit = tmp_path / 'audit.log'
    if existing:
        log.write_text('unchanged')
        audit.write_text('unchanged')
    config = tmp_path / '.myclirc'
    content = f'[main]\nlog_file = {log}\naudit_log = {audit}\n[alias_dsn]\nprod = mysql://host/db\n'
    config.write_text(content)

    result = CliRunner().invoke(main.click_entrypoint, ['--list-dsn'])

    assert result.exit_code == 0
    assert config.read_text() == content
    for path in (log, audit):
        assert path.exists() == existing
        if existing:
            assert path.read_text() == 'unchanged'


def test_list_dsn_skips_unrelated_client_settings(tmp_path: Path) -> None:
    (tmp_path / '.myclirc').write_text(
        '[main]\ntable_format = not-a-format\nbeep_after_seconds = invalid\n[alias_dsn]\nprod = mysql://host/db\n'
    )

    result = CliRunner().invoke(main.click_entrypoint, ['--list-dsn'])

    assert result.exit_code == 0
    assert result.output == 'prod\n'


@pytest.mark.parametrize(
    ('flags', 'expected'), [([], 'prod\n'), (['--quiet'], 'prod\n'), (['--verbose'], 'prod : mysql://${USER}@host/db\n')]
)
def test_list_dsn_preserves_verbosity_and_raw_values(tmp_path: Path, flags: list[str], expected: str) -> None:
    (tmp_path / '.myclirc').write_text(
        '[main]\nless_chatty = true\n[alias_dsn]\nprod = mysql://${USER}@host/db\n-hidden = mysql://hidden/db\n'
    )

    result = CliRunner().invoke(main.click_entrypoint, ['--list-dsn', *flags])

    assert result.exit_code == 0
    assert result.output == expected


def test_list_dsn_reports_relative_shared_path(tmp_path: Path) -> None:
    (tmp_path / '.myclirc').write_text('[main]\nshared_dsns_file = relative\n[alias_dsn]\nprod = mysql://host/db\n')

    result = CliRunner().invoke(main.click_entrypoint, ['--list-dsn'])

    assert result.exit_code == 0
    assert "Shared DSNs file path must be absolute: 'relative'." in result.stderr
    assert result.stdout == 'prod\n'


def test_list_dsn_keeps_valid_entries_in_malformed_config(tmp_path: Path) -> None:
    (tmp_path / '.myclirc').write_text('[alias_dsn]\nprod = mysql://host/db\n[invalid\n')

    result = CliRunner().invoke(main.click_entrypoint, ['--list-dsn'])

    assert result.exit_code == 0
    assert 'Unable to parse line 3' in result.stderr
    assert result.stdout == 'prod\n'


@pytest.mark.parametrize('flags', [['--verbose', '--quiet'], ['--csv', '--format', 'table'], ['--table', '--format', 'csv'], ['--resume']])
def test_list_dsn_preserves_argument_errors(flags: list[str], monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(cli_runner, 'load_list_dsn_config', lambda path: pytest.fail('config loaded'))

    result = CliRunner().invoke(main.click_entrypoint, ['--list-dsn', *flags])

    assert result.exit_code == 1
    assert 'Error:' in result.output or 'Conflicting' in result.output


def test_completions_take_precedence_over_list_dsn(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(cli_runner, 'load_list_dsn_config', lambda path: pytest.fail('config loaded'))
    monkeypatch.setattr(cli_runner, 'main_completions', lambda shell: None)

    result = CliRunner().invoke(main.click_entrypoint, ['--list-dsn', '--completions', 'bash'])

    assert result.exit_code == 0


def test_checkup_takes_precedence_over_list_dsn(monkeypatch: pytest.MonkeyPatch) -> None:
    client = object()
    monkeypatch.setattr(client_module, 'MyCli', lambda **kwargs: client)
    monkeypatch.setattr(cli_runner, 'load_list_dsn_config', lambda path: pytest.fail('config loaded'))
    calls: list[object] = []
    monkeypatch.setattr(cli_runner, 'main_checkup', calls.append)

    result = CliRunner().invoke(main.click_entrypoint, ['--list-dsn', '--checkup', '--csv', '--format', 'table'])

    assert result.exit_code == 0
    assert calls == [client]


@pytest.mark.skipif(sys.version_info < (3, 15), reason='Native lazy imports require Python 3.15.')
def test_list_dsn_does_not_import_runtime_dependencies(tmp_path: Path) -> None:
    config = tmp_path / 'myclirc'
    config.write_text('[alias_dsn]\nprod = mysql://host/db\n')
    script = '''
import sys
from mycli import config
config.SYSTEM_CONFIG_FILES = []
from mycli.main import click_entrypoint
try:
    click_entrypoint.main(['--list-dsn', '--myclirc', sys.argv[1]], standalone_mode=False)
except SystemExit as exc:
    assert exc.code == 0
prefixes = ('mycli.client', 'mycli.main_modes.repl', 'mycli.packages.special_commands',
            'sqlglot', 'prompt_toolkit', 'llm', 'pymysql', 'keyring', 'Cryptodome.Cipher.AES')
loaded = sorted(name for name in sys.modules if any(name == prefix or name.startswith(prefix + '.') for prefix in prefixes))
assert not loaded, loaded
'''
    env = dict(os.environ)
    env.pop('PYTHONPATH', None)
    result = subprocess.run([sys.executable, '-c', script, str(config)], env=env, text=True, capture_output=True, timeout=30)

    assert result.returncode == 0, result.stderr
    assert result.stdout == 'prod\n'
