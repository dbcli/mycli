from __future__ import annotations

import functools
import subprocess

DEFAULT_VAULT_EXECUTABLE = 'vault'
DEFAULT_VAULT_PASSWORD_FIELD = 'password'
DEFAULT_VAULT_USERNAME_FIELD = 'username'


class VaultError(RuntimeError):
    pass


@functools.lru_cache(maxsize=32)
def _ensure_vault_user_logged_in(
    executable: str = DEFAULT_VAULT_EXECUTABLE,
    address: str | None = None,
) -> None:
    command = [
        executable,
        'token',
        'lookup',
        '-format=json',
    ]
    if address:
        command.append(f'-address={address}')

    try:
        completed_process = subprocess.run(
            command,
            check=False,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
    except FileNotFoundError as exc:
        raise VaultError(f'Vault executable not found: {executable}') from exc
    except OSError as exc:
        raise VaultError(f'Unable to run Vault executable {executable}: {exc}') from exc

    if completed_process.returncode:
        # maybe could display something from the JSON output
        # maybe only with --verbose
        raise VaultError('Not logged in to Vault. You may need to run "vault login".')


def get_field_from_vault(
    field: str,
    secret: str,
    executable: str = DEFAULT_VAULT_EXECUTABLE,
    mount: str | None = None,
    address: str | None = None,
) -> str:

    _ensure_vault_user_logged_in(
        executable=executable,
        address=address,
    )

    command = [
        executable,
        'kv',
        'get',
        f'-field={field}',
    ]
    if mount:
        command.append(f'-mount={mount}')
    if address:
        command.append(f'-address={address}')

    command.append(secret)

    try:
        completed_process = subprocess.run(
            command,
            check=False,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
    except FileNotFoundError as exc:
        raise VaultError(f'Vault executable not found: {executable}') from exc
    except OSError as exc:
        raise VaultError(f'Unable to run Vault executable {executable}: {exc}') from exc

    if completed_process.returncode:
        stderr = completed_process.stderr.strip()
        if stderr:
            raise VaultError(f'Vault command failed. You may need to run "vault login": {stderr}')
        raise VaultError(f'Vault command failed. You may need to run "vault login". Exit code {completed_process.returncode}.')

    return completed_process.stdout.removesuffix('\n')
