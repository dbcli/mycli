from __future__ import annotations

import subprocess
from types import SimpleNamespace
from typing import Any

import pytest

from mycli import vault


def test_get_field_from_vault_runs_kv_get_with_field_mount_and_address(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run_calls: list[dict[str, Any]] = []

    def fake_run(command: list[str], **kwargs: Any) -> SimpleNamespace:
        run_calls.append({'command': command, **kwargs})
        return SimpleNamespace(returncode=0, stdout='secret\n', stderr='')

    monkeypatch.setattr(vault.subprocess, 'run', fake_run)

    password = vault.get_field_from_vault(
        'mysql_password',
        'database/prod',
        executable='/opt/bin/vault',
        mount='kv',
        address='https://vault.example.com',
    )

    assert password == 'secret'
    assert run_calls == [
        {
            'command': [
                '/opt/bin/vault',
                'kv',
                'get',
                '-field=mysql_password',
                '-mount=kv',
                '-address=https://vault.example.com',
                'database/prod',
            ],
            'check': False,
            'stdin': subprocess.DEVNULL,
            'stdout': subprocess.PIPE,
            'stderr': subprocess.PIPE,
            'text': True,
        }
    ]


def test_get_field_from_vault_reports_missing_executable(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_run(*_args: Any, **_kwargs: Any) -> SimpleNamespace:
        raise FileNotFoundError()

    monkeypatch.setattr(vault.subprocess, 'run', fake_run)

    with pytest.raises(vault.VaultError, match='Vault executable not found: missing-vault'):
        vault.get_field_from_vault('password', 'database/prod', executable='missing-vault')


def test_get_field_from_vault_reports_oserror(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_run(*_args: Any, **_kwargs: Any) -> SimpleNamespace:
        raise OSError('boom')

    monkeypatch.setattr(vault.subprocess, 'run', fake_run)

    with pytest.raises(vault.VaultError, match='Unable to run Vault executable vault: boom'):
        vault.get_field_from_vault('password', 'database/prod')


def test_get_field_from_vault_reports_nonzero_exit_without_stdout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_run(*_args: Any, **_kwargs: Any) -> SimpleNamespace:
        return SimpleNamespace(returncode=2, stdout='secret\n', stderr='permission denied\n')

    monkeypatch.setattr(vault.subprocess, 'run', fake_run)

    with pytest.raises(vault.VaultError) as excinfo:
        vault.get_field_from_vault('password', 'database/prod')

    assert 'permission denied' in str(excinfo.value)
    assert 'secret' not in str(excinfo.value)


def test_get_field_from_vault_reports_nonzero_exit_without_stderr(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_run(*_args: Any, **_kwargs: Any) -> SimpleNamespace:
        return SimpleNamespace(returncode=2, stdout='', stderr='')

    monkeypatch.setattr(vault.subprocess, 'run', fake_run)

    with pytest.raises(vault.VaultError, match='Vault command failed\\. You may need to run "vault login"\\. Exit code 2\\.'):
        vault.get_field_from_vault('password', 'database/prod')
