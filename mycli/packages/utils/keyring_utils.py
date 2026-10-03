import sys

import keyring
from keyring.backend import KeyringBackend


def _set_password_with_backend(backend: KeyringBackend, service: str, account: str, password: str) -> None:
    from keyring.backends.macOS import Keyring

    if type(backend) is Keyring:
        from mycli import macos_keychain

        macos_keychain.set_password(service, account, password)
    else:
        backend.set_password(service, account, password)


def set_keyring_password(service: str, account: str, password: str) -> None:
    if sys.platform != 'darwin':
        keyring.set_password(service, account, password)
        return

    from keyring.backends.chainer import ChainerBackend  # type: ignore[unreachable]

    backend = keyring.get_keyring()
    if type(backend) is ChainerBackend:
        for candidate in backend.backends:
            try:
                _set_password_with_backend(candidate, service, account, password)
                return
            except NotImplementedError:
                continue
    else:
        _set_password_with_backend(backend, service, account, password)
