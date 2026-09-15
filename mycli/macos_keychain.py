import ctypes
from typing import Any

from keyring.errors import KeyringLocked, PasswordSetError


def _get_api() -> Any:
    from keyring.backends.macOS import api

    return api


def set_password(service: str, account: str, password: str) -> None:
    """Preserve existing ACLs and create credentials without trusting Python."""
    api = _get_api()
    cf_array_create = api._found.CFArrayCreate
    cf_array_create.restype = ctypes.c_void_p
    cf_array_create.argtypes = (ctypes.c_void_p, ctypes.c_void_p, ctypes.c_long, ctypes.c_void_p)
    cf_data_create = api._found.CFDataCreate
    cf_data_create.restype = ctypes.c_void_p
    cf_data_create.argtypes = (ctypes.c_void_p, ctypes.c_void_p, ctypes.c_long)
    cf_release = api._found.CFRelease
    cf_release.restype = None
    cf_release.argtypes = (ctypes.c_void_p,)
    sec_access_create = api._sec.SecAccessCreate
    sec_access_create.restype = api.OS_status
    sec_access_create.argtypes = (ctypes.c_void_p, ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p))
    sec_item_update = api._sec.SecItemUpdate
    sec_item_update.restype = api.OS_status
    sec_item_update.argtypes = (ctypes.c_void_p, ctypes.c_void_p)

    retained: list[ctypes.c_void_p] = []

    def retain(value: int | ctypes.c_void_p | None, name: str) -> ctypes.c_void_p:
        if not value:
            raise RuntimeError(f'Unable to allocate Keychain {name}')
        pointer = value if isinstance(value, ctypes.c_void_p) else ctypes.c_void_p(value)
        retained.append(pointer)
        return pointer

    try:
        service_value = retain(api.create_cf(service), 'service')
        account_value = retain(api.create_cf(account), 'account')
        encoded = password.encode('utf-8')
        password_value = retain(cf_data_create(None, ctypes.create_string_buffer(encoded), len(encoded)), 'password')
        search = retain(
            api.create_query(
                kSecClass=api.k_('kSecClassGenericPassword'),
                kSecAttrService=service_value,
                kSecAttrAccount=account_value,
            ),
            'search',
        )
        attributes = retain(api.create_query(kSecValueData=password_value), 'attributes')
        status = sec_item_update(search, attributes)
        if status == api.error.item_not_found:
            # An empty array trusts nobody; NULL would trust the calling executable.
            trusted_apps = retain(cf_array_create(None, None, 0, None), 'access controls')
            access = ctypes.c_void_p()
            api.Error.raise_for_status(sec_access_create(service_value, trusted_apps, ctypes.byref(access)))
            retain(access, 'access')
            item = retain(
                api.create_query(
                    kSecClass=api.k_('kSecClassGenericPassword'),
                    kSecAttrService=service_value,
                    kSecAttrAccount=account_value,
                    kSecValueData=password_value,
                    kSecAttrAccess=access,
                ),
                'item',
            )
            status = api.SecItemAdd(item, None)
        api.Error.raise_for_status(status)
    except api.KeychainDenied as e:
        raise KeyringLocked(f"Can't store password on keychain: {e}") from e
    except api.Error as e:
        raise PasswordSetError(f"Can't store password on keychain: {e}") from e
    finally:
        for value in reversed(retained):
            cf_release(value)
