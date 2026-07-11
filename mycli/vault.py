from __future__ import annotations

import subprocess

DEFAULT_VAULT_EXECUTABLE = 'vault'
DEFAULT_VAULT_FIELD = 'password'


class VaultError(RuntimeError):
    pass


def get_password_from_vault(
    *,
    secret: str,
    executable: str = DEFAULT_VAULT_EXECUTABLE,
    field: str = DEFAULT_VAULT_FIELD,
    mount: str | None = None,
    address: str | None = None,
) -> str:
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
