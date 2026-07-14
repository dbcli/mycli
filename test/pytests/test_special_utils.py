# type: ignore

import os
import pathlib
import tempfile
from types import SimpleNamespace
from unittest.mock import MagicMock

import pymysql
import pytest

import mycli.packages.special.utils
from mycli.packages.special.utils import (
    CACHED_SSL_VERSION,
    compute_current_dsn,
    format_connection_dsn,
    format_uptime,
    get_local_timezone,
    get_server_timezone,
    get_ssl_cipher,
    get_ssl_version,
    get_uptime,
    get_warning_count,
    handle_cd_command,
)
from test.utils import TEMPFILE_PREFIX


@pytest.fixture(autouse=True)
def clear_ssl_cache() -> None:
    CACHED_SSL_VERSION.clear()


def test_handle_cd_command_rejects_non_cd_command() -> None:
    handled, message = handle_cd_command(['pwd'])

    assert handled is False
    assert message == 'Not a cd command.'


def test_handle_cd_command_requires_exactly_one_directory() -> None:
    handled, message = handle_cd_command(['cd'])

    assert handled is False
    assert message == 'Exactly one directory name must be provided.'


@pytest.mark.skipif(os.name == 'nt', reason='todo: unknown')
def test_handle_cd_command_changes_directory_and_echoes_cwd(monkeypatch) -> None:
    echoed = []

    monkeypatch.setattr(mycli.packages.special.utils.click, 'echo', lambda message, err=False: echoed.append((message, err)))
    monkeypatch.chdir(os.getcwd())

    # resolve() is needed for mac /private/var arrangement
    with tempfile.TemporaryDirectory(prefix=TEMPFILE_PREFIX) as tempdir:
        tempdir_resolved = str(pathlib.Path(tempdir).resolve())
        handled, message = handle_cd_command(['cd', tempdir_resolved])
        assert str(pathlib.Path(os.getcwd()).resolve()) == tempdir_resolved
        assert handled is True
        assert message is None
        assert echoed == [(tempdir_resolved, True)]


def test_handle_cd_command_returns_oserror_message(monkeypatch) -> None:
    def raise_oserror(directory: str) -> None:
        raise OSError(2, 'No such file or directory')

    monkeypatch.setattr(mycli.packages.special.utils.os, 'chdir', raise_oserror)

    handled, message = handle_cd_command(['cd', '/missing'])

    assert handled is False
    assert message == 'No such file or directory'


def test_format_uptime():
    seconds = 59
    assert '59 sec' == format_uptime(seconds)

    seconds = 120
    assert '2 min 0 sec' == format_uptime(seconds)

    seconds = 54890
    assert '15 hours 14 min 50 sec' == format_uptime(seconds)

    seconds = 598244
    assert '6 days 22 hours 10 min 44 sec' == format_uptime(seconds)

    seconds = 522600
    assert '6 days 1 hour 10 min 0 sec' == format_uptime(seconds)


def test_format_uptime_uses_singular_units() -> None:
    assert format_uptime('90061') == '1 day 1 hour 1 min 1 sec'


def test_get_uptime_returns_value_from_status_row() -> None:
    cur = MagicMock()
    cur.fetchone.return_value = ('Uptime', '15')

    uptime = get_uptime(cur)

    cur.execute.assert_called_once_with('SHOW STATUS LIKE "Uptime"')
    assert uptime == 15


def test_get_uptime_defaults_to_zero_for_missing_value() -> None:
    cur = MagicMock()
    cur.fetchone.return_value = ('Uptime', None)

    assert get_uptime(cur) == 0


def test_get_uptime_ignores_operational_error() -> None:
    cur = MagicMock()
    cur.execute.side_effect = pymysql.err.OperationalError()

    assert get_uptime(cur) == 0


def test_get_warning_count_returns_value_from_count_row() -> None:
    cur = MagicMock()
    cur.fetchone.return_value = ('7',)

    warning_count = get_warning_count(cur)

    cur.execute.assert_called_once_with('SHOW COUNT(*) WARNINGS')
    assert warning_count == 7


def test_get_warning_count_defaults_to_zero_for_missing_value() -> None:
    cur = MagicMock()
    cur.fetchone.return_value = (None,)

    assert get_warning_count(cur) == 0


def test_get_warning_count_ignores_operational_error() -> None:
    cur = MagicMock()
    cur.execute.side_effect = pymysql.err.OperationalError()

    assert get_warning_count(cur) == 0


def test_get_ssl_version_fetches_and_caches_value() -> None:
    cur = MagicMock()
    cur.connection = MagicMock()
    cur.connection.thread_id.return_value = 42
    cur.fetchone.return_value = ('Ssl_version', 'TLSv1.3')

    first = get_ssl_version(cur)
    second = get_ssl_version(cur)

    cur.execute.assert_called_once_with('SHOW STATUS LIKE "Ssl_version"')
    assert first == 'TLSv1.3'
    assert second == 'TLSv1.3'


def test_get_ssl_version_caches_missing_row_as_none() -> None:
    cur = MagicMock()
    cur.connection = MagicMock()
    cur.connection.thread_id.return_value = 42
    cur.fetchone.return_value = None

    first = get_ssl_version(cur)
    second = get_ssl_version(cur)

    cur.execute.assert_called_once_with('SHOW STATUS LIKE "Ssl_version"')
    assert first is None
    assert second is None


def test_get_ssl_version_returns_none_for_empty_value_and_caches_it() -> None:
    cur = MagicMock()
    cur.connection = MagicMock()
    cur.connection.thread_id.return_value = 42
    cur.fetchone.return_value = ('Ssl_version', '')

    first = get_ssl_version(cur)
    second = get_ssl_version(cur)

    cur.execute.assert_called_once_with('SHOW STATUS LIKE "Ssl_version"')
    assert first is None
    assert second is None


def test_get_ssl_version_ignores_operational_error() -> None:
    cur = MagicMock()
    cur.connection = MagicMock()
    cur.connection.thread_id.return_value = 42
    cur.execute.side_effect = pymysql.err.OperationalError()

    assert get_ssl_version(cur) is None


def test_get_ssl_cipher_returns_value() -> None:
    cur = MagicMock()
    cur.fetchone.return_value = ('Ssl_cipher', 'TLS_AES_256_GCM_SHA384')

    ssl_cipher = get_ssl_cipher(cur)

    cur.execute.assert_called_once_with('SHOW STATUS LIKE "Ssl_cipher"')
    assert ssl_cipher == 'TLS_AES_256_GCM_SHA384'


def test_get_ssl_cipher_returns_none_for_missing_row() -> None:
    cur = MagicMock()
    cur.fetchone.return_value = None

    assert get_ssl_cipher(cur) is None


def test_get_ssl_cipher_returns_none_for_empty_value() -> None:
    cur = MagicMock()
    cur.fetchone.return_value = ('Ssl_cipher', '')

    assert get_ssl_cipher(cur) is None


def test_get_ssl_cipher_ignores_operational_error() -> None:
    cur = MagicMock()
    cur.execute.side_effect = pymysql.err.OperationalError()

    assert get_ssl_cipher(cur) is None


def test_get_server_timezone_prefers_system_timezone_when_requested() -> None:
    variables = {
        'time_zone': 'SYSTEM',
        'system_time_zone': 'UTC',
    }

    assert get_server_timezone(variables) == 'UTC'


def test_get_server_timezone_returns_explicit_timezone() -> None:
    variables = {
        'time_zone': '+02:00',
        'system_time_zone': 'UTC',
    }

    assert get_server_timezone(variables) == '+02:00'


def test_get_server_timezone_returns_empty_string_when_keys_are_missing() -> None:
    assert get_server_timezone({}) == ''


def test_get_local_timezone_returns_tzname(monkeypatch) -> None:
    class FakeAwareDatetime:
        def tzname(self) -> str:
            return 'EDT'

    class FakeDatetime:
        @staticmethod
        def now() -> 'FakeDatetime':
            return FakeDatetime()

        def astimezone(self) -> FakeAwareDatetime:
            return FakeAwareDatetime()

    monkeypatch.setattr(mycli.packages.special.utils.datetime, 'datetime', FakeDatetime)

    assert get_local_timezone() == 'EDT'


def test_get_local_timezone_returns_empty_string_when_tzname_is_none(monkeypatch) -> None:
    class FakeAwareDatetime:
        def tzname(self) -> None:
            return None

    class FakeDatetime:
        @staticmethod
        def now() -> 'FakeDatetime':
            return FakeDatetime()

        def astimezone(self) -> FakeAwareDatetime:
            return FakeAwareDatetime()

    monkeypatch.setattr(mycli.packages.special.utils.datetime, 'datetime', FakeDatetime)

    assert get_local_timezone() == ''


def test_compute_current_dsn_for_tcp_connection() -> None:
    connection = SimpleNamespace(
        user='user@example.com',
        host='db.example.com',
        port=3307,
        db='my db',
        unix_socket=None,
        charset='utf8mb4',
    )
    cursor = SimpleNamespace(connection=connection)

    assert compute_current_dsn(cursor) == 'mysql://user%40example.com@db.example.com:3307/my%20db'


def test_compute_current_dsn_prefers_mycli_display_dsn() -> None:
    connection = SimpleNamespace(
        _mycli_display_dsn='mysql://alice@db.example.com:3307/prod',
        user='alice',
        host='localhost',
        port=4406,
        db='prod',
        unix_socket=None,
        charset='utf8mb4',
    )
    cursor = SimpleNamespace(connection=connection)

    assert compute_current_dsn(cursor) == 'mysql://alice@db.example.com:3307/prod'


def test_format_connection_dsn_includes_ssh_jump() -> None:
    assert (
        format_connection_dsn(
            user='alice',
            host='db.example.com',
            port=3307,
            database='prod',
            socket=None,
            character_set='utf8mb4',
            ssh_jump='bastion',
        )
        == 'mysql://alice@db.example.com:3307/prod?ssh_jump=bastion'
    )


def test_format_connection_dsn_includes_vault_parameters() -> None:
    assert format_connection_dsn(
        user=None,
        host='db.example.com',
        port=3307,
        database='prod',
        socket=None,
        character_set='utf8mb4',
        vault_address='https://vault.example.com',
        vault_mount='kv',
        vault_secret='database/prod',
        vault_password_field='mysql_password',
        vault_username_field='mysql_username',
    ) == (
        'mysql://db.example.com:3307/prod?vault_address=https%3A%2F%2Fvault.example.com'
        '&vault_mount=kv&vault_secret=database%2Fprod&vault_password_field=mysql_password'
        '&vault_username_field=mysql_username'
    )


def test_compute_current_dsn_for_socket_connection() -> None:
    connection = SimpleNamespace(
        user='alice',
        host='localhost',
        port=3306,
        db='',
        unix_socket='/tmp/mysql.sock',
        charset='utf8mb4',
    )
    cursor = SimpleNamespace(connection=connection)

    assert compute_current_dsn(cursor) == 'mysql://alice@localhost?socket=%2Ftmp%2Fmysql.sock'


def test_compute_current_dsn_includes_non_default_character_set() -> None:
    connection = SimpleNamespace(
        user='alice',
        host=None,
        port=3306,
        db=b'mysql',
        unix_socket=None,
        charset='latin1',
    )
    cursor = SimpleNamespace(connection=connection)

    assert compute_current_dsn(cursor) == 'mysql://alice@localhost:3306/mysql?character_set=latin1'
