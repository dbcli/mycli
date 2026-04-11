# type: ignore

import pytest

from mycli.constants import EMPTY_PASSWORD_FLAG_SENTINEL
from mycli.packages import cli_utils
from mycli.packages.cli_utils import (
    filtered_sys_argv,
    is_valid_connection_scheme,
)


@pytest.mark.parametrize(
    ('argv', 'expected'),
    [
        (['mycli', '-h'], ['--help']),
        (['mycli', '-h', 'example.com'], ['-h', 'example.com']),
    ],
)
def test_filtered_sys_argv(monkeypatch, argv, expected):
    monkeypatch.setattr(cli_utils.sys, 'argv', argv)

    assert filtered_sys_argv() == expected


@pytest.mark.parametrize('password_flag', ['-p', '--pass', '--password'])
def test_filtered_sys_argv_appends_empty_password_sentinel(monkeypatch, password_flag):
    monkeypatch.setattr(cli_utils.sys, 'argv', ['mycli', 'database', password_flag])

    assert filtered_sys_argv() == ['database', password_flag, EMPTY_PASSWORD_FLAG_SENTINEL]


@pytest.mark.parametrize(
    ('text', 'is_valid', 'invalid_scheme'),
    [
        ('localhost', False, None),
        ('mysql://user@localhost/db', True, None),
        ('mysqlx://user@localhost/db', True, None),
        ('tcp://localhost:3306', True, None),
        ('socket:///tmp/mysql.sock', True, None),
        ('ssh://user@example.com', True, None),
        ('postgres://user@localhost/db', False, 'postgres'),
        ('http://example.com', False, 'http'),
    ],
)
def test_is_valid_connection_scheme(text, is_valid, invalid_scheme):
    assert is_valid_connection_scheme(text) == (is_valid, invalid_scheme)
