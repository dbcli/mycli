import ctypes
from types import SimpleNamespace
from typing import Any
from unittest.mock import Mock

from keyring.backends import macOS
from keyring.errors import KeyringLocked, PasswordSetError
import pytest

from mycli import macos_keychain


class ApiError(Exception):
    @classmethod
    def raise_for_status(cls, status: int) -> None:
        if status == -128:
            raise ApiDenied(status)
        if status:
            raise cls(status)


class ApiDenied(ApiError):
    pass


@pytest.fixture
def api(monkeypatch: pytest.MonkeyPatch) -> SimpleNamespace:
    def create_access(descriptor: ctypes.c_void_p, apps: ctypes.c_void_p, result: Any) -> int:
        ctypes.cast(result, ctypes.POINTER(ctypes.c_void_p))[0] = ctypes.c_void_p(205)
        return 0

    api = SimpleNamespace(
        _found=SimpleNamespace(CFArrayCreate=Mock(return_value=204), CFDataCreate=Mock(return_value=103), CFRelease=Mock()),
        _sec=SimpleNamespace(SecAccessCreate=Mock(side_effect=create_access), SecItemUpdate=Mock(return_value=0)),
        OS_status=ctypes.c_int32,
        error=SimpleNamespace(item_not_found=-25300),
        Error=ApiError,
        KeychainDenied=ApiDenied,
        create_cf=Mock(side_effect=[101, 102]),
        create_query=Mock(side_effect=[201, 202, 203]),
        k_=Mock(return_value=ctypes.c_void_p(301)),
        SecItemAdd=Mock(return_value=0),
    )
    monkeypatch.setattr(macos_keychain, '_get_api', lambda: api)
    return api


def released(api: SimpleNamespace) -> list[int]:
    return [call.args[0].value for call in api._found.CFRelease.call_args_list]


def test_api_is_imported_lazily(monkeypatch: pytest.MonkeyPatch) -> None:
    sentinel = object()
    monkeypatch.setattr(macOS, 'api', sentinel, raising=False)

    assert macos_keychain._get_api() is sentinel


def test_update_preserves_access_controls(api: SimpleNamespace) -> None:
    macos_keychain.set_password('mycli.net', 'account', 'secret')

    assert list(api.create_query.call_args_list[1].kwargs) == ['kSecValueData']
    api._found.CFArrayCreate.assert_not_called()
    api._sec.SecAccessCreate.assert_not_called()
    api.SecItemAdd.assert_not_called()
    assert released(api) == [202, 201, 103, 102, 101]


def test_create_has_no_trusted_applications(api: SimpleNamespace) -> None:
    api._sec.SecItemUpdate.return_value = api.error.item_not_found

    macos_keychain.set_password('mycli.net', 'account', 'secret')

    api._found.CFArrayCreate.assert_called_once_with(None, None, 0, None)
    assert api._sec.SecAccessCreate.call_args.args[1].value == 204
    item = api.create_query.call_args_list[2].kwargs
    assert item['kSecAttrAccess'].value == 205
    assert item['kSecAttrService'].value == 101
    assert item['kSecAttrAccount'].value == 102
    assert item['kSecValueData'].value == 103
    assert api.SecItemAdd.call_args.args[0].value == 203
    assert released(api) == [203, 205, 204, 202, 201, 103, 102, 101]


@pytest.mark.parametrize('password', ['secret', 'p\u00e4ss\U0001f512', 'with\0null', ''])
def test_password_is_utf8_data(api: SimpleNamespace, password: str) -> None:
    macos_keychain.set_password('service', 'account', password)

    _, buffer, length = api._found.CFDataCreate.call_args.args
    assert ctypes.string_at(buffer, length) == password.encode('utf-8')
    assert [call.args[0] for call in api.create_cf.call_args_list] == ['service', 'account']


@pytest.mark.parametrize(
    ('operation', 'released_values'),
    [
        ('update', [202, 201, 103, 102, 101]),
        ('access', [204, 202, 201, 103, 102, 101]),
        ('add', [203, 205, 204, 202, 201, 103, 102, 101]),
    ],
)
@pytest.mark.parametrize(('status', 'exception'), [(-128, KeyringLocked), (-50, PasswordSetError)])
def test_native_errors_release_resources(
    api: SimpleNamespace, operation: str, released_values: list[int], status: int, exception: type[Exception]
) -> None:
    api._sec.SecItemUpdate.return_value = api.error.item_not_found
    if operation == 'update':
        api._sec.SecItemUpdate.return_value = status
    elif operation == 'access':
        api._sec.SecAccessCreate.side_effect = None
        api._sec.SecAccessCreate.return_value = status
    else:
        api.SecItemAdd.return_value = status

    with pytest.raises(exception, match="Can't store password on keychain"):
        macos_keychain.set_password('service', 'account', 'secret')

    assert released(api) == released_values
    if operation != 'add':
        api.SecItemAdd.assert_not_called()


@pytest.mark.parametrize(
    ('allocation', 'released_values'),
    [
        ('service', []),
        ('account', [101]),
        ('password', [102, 101]),
        ('search', [103, 102, 101]),
        ('attributes', [201, 103, 102, 101]),
        ('access controls', [202, 201, 103, 102, 101]),
        ('access', [204, 202, 201, 103, 102, 101]),
        ('item', [205, 204, 202, 201, 103, 102, 101]),
    ],
)
def test_allocation_failure_is_not_an_unrestricted_write(api: SimpleNamespace, allocation: str, released_values: list[int]) -> None:
    api._sec.SecItemUpdate.return_value = api.error.item_not_found
    if allocation == 'service':
        api.create_cf.side_effect = [None]
    elif allocation == 'account':
        api.create_cf.side_effect = [101, None]
    elif allocation == 'password':
        api._found.CFDataCreate.return_value = None
    elif allocation == 'search':
        api.create_query.side_effect = [None]
    elif allocation == 'attributes':
        api.create_query.side_effect = [201, None]
    elif allocation == 'access controls':
        api._found.CFArrayCreate.return_value = None
    elif allocation == 'access':
        api._sec.SecAccessCreate.side_effect = None
        api._sec.SecAccessCreate.return_value = 0
    else:
        api.create_query.side_effect = [201, 202, None]

    with pytest.raises(RuntimeError, match=f'Unable to allocate Keychain {allocation}'):
        macos_keychain.set_password('service', 'account', 'secret')

    api.SecItemAdd.assert_not_called()
    assert released(api) == released_values
