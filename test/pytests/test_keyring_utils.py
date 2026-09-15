from unittest.mock import Mock

from keyring.backends.chainer import ChainerBackend
from keyring.backends.macOS import Keyring
import pytest

from mycli import keyring_utils, macos_keychain


@pytest.fixture
def native_write(monkeypatch: pytest.MonkeyPatch) -> Mock:
    write = Mock()
    monkeypatch.setattr(keyring_utils.sys, 'platform', 'darwin')
    monkeypatch.setattr(macos_keychain, 'set_password', write)
    return write


@pytest.mark.parametrize('platform', ['linux', 'win32'])
def test_other_platforms_use_configured_keyring(monkeypatch: pytest.MonkeyPatch, platform: str) -> None:
    write = Mock()
    monkeypatch.setattr(keyring_utils.sys, 'platform', platform)
    monkeypatch.setattr(keyring_utils.keyring, 'set_password', write)
    monkeypatch.setattr(keyring_utils.keyring, 'get_keyring', Mock(side_effect=AssertionError('Do not inspect backend')))

    keyring_utils.set_keyring_password('mycli.net', 'account', 'secret')

    write.assert_called_once_with('mycli.net', 'account', 'secret')


@pytest.mark.parametrize('chained', [False, True])
def test_native_backend_uses_restricted_writer(monkeypatch: pytest.MonkeyPatch, native_write: Mock, chained: bool) -> None:
    backend = Keyring()
    monkeypatch.setattr(backend, 'set_password', Mock(side_effect=AssertionError('Unsafe native write')))
    monkeypatch.setattr(ChainerBackend, 'backends', [backend])
    monkeypatch.setattr(keyring_utils.keyring, 'get_keyring', lambda: ChainerBackend() if chained else backend)

    keyring_utils.set_keyring_password('mycli.net', 'account', 'secret')

    native_write.assert_called_once_with('mycli.net', 'account', 'secret')


def test_custom_backend_is_not_unwrapped(monkeypatch: pytest.MonkeyPatch, native_write: Mock) -> None:
    backend = Mock(backends=[Keyring()])
    monkeypatch.setattr(keyring_utils.keyring, 'get_keyring', lambda: backend)

    keyring_utils.set_keyring_password('service', 'account', 'secret')

    backend.set_password.assert_called_once_with('service', 'account', 'secret')
    native_write.assert_not_called()


def test_native_subclass_retains_custom_write(monkeypatch: pytest.MonkeyPatch, native_write: Mock) -> None:
    class CustomKeyring(Keyring):
        pass

    backend = CustomKeyring()
    write = Mock()
    monkeypatch.setattr(backend, 'set_password', write)
    monkeypatch.setattr(keyring_utils.keyring, 'get_keyring', lambda: backend)

    keyring_utils.set_keyring_password('service', 'account', 'secret')

    write.assert_called_once_with('service', 'account', 'secret')
    native_write.assert_not_called()


@pytest.mark.parametrize('read_only', [False, True])
def test_chainer_preserves_backend_order(monkeypatch: pytest.MonkeyPatch, native_write: Mock, read_only: bool) -> None:
    first = Mock()
    if read_only:
        first.set_password.side_effect = NotImplementedError
    monkeypatch.setattr(ChainerBackend, 'backends', [first, Keyring()])
    monkeypatch.setattr(keyring_utils.keyring, 'get_keyring', ChainerBackend)

    keyring_utils.set_keyring_password('service', 'account', 'secret')

    first.set_password.assert_called_once_with('service', 'account', 'secret')
    assert native_write.call_count == int(read_only)


@pytest.mark.parametrize('chained', [False, True])
def test_native_failure_never_falls_back(monkeypatch: pytest.MonkeyPatch, native_write: Mock, chained: bool) -> None:
    native_write.side_effect = RuntimeError('denied')
    fallback = Mock()
    backend = Keyring()
    monkeypatch.setattr(backend, 'set_password', Mock(side_effect=AssertionError('Unsafe native write')))
    monkeypatch.setattr(ChainerBackend, 'backends', [backend, fallback])
    monkeypatch.setattr(keyring_utils.keyring, 'get_keyring', lambda: ChainerBackend() if chained else backend)

    with pytest.raises(RuntimeError, match='denied'):
        keyring_utils.set_keyring_password('service', 'account', 'secret')

    fallback.set_password.assert_not_called()


def test_read_only_chainer_keeps_existing_behavior(monkeypatch: pytest.MonkeyPatch, native_write: Mock) -> None:
    backend = Mock()
    backend.set_password.side_effect = NotImplementedError
    monkeypatch.setattr(ChainerBackend, 'backends', [backend])
    monkeypatch.setattr(keyring_utils.keyring, 'get_keyring', ChainerBackend)

    keyring_utils.set_keyring_password('service', 'account', 'secret')

    backend.set_password.assert_called_once()
    native_write.assert_not_called()
