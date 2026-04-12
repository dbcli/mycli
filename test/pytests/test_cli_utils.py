# type: ignore

import pytest

from mycli.packages import cli_utils
from mycli.packages.cli_utils import (
    _normalize_password_args,
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


@pytest.mark.parametrize(
    ('args', 'expected_args', 'expected_password'),
    [
        # --password / --pass with a dash-prefixed value: extracted from args
        (['--password', '-mypass'], [], '-mypass'),
        (['--pass', '-mypass'], [], '-mypass'),
        # --password=-mypass / --pass=-mypass: extracted from args
        (['--password=-mypass'], [], '-mypass'),
        (['--pass=-mypass'], [], '-mypass'),
        # -p-mypass: extracted from args
        (['-p-mypass'], [], '-mypass'),
        # --password with a normal value is left for Click
        (['--password', 'mypass'], ['--password', 'mypass'], None),
        (['--password=mypass'], ['--password=mypass'], None),
        # --password with -- (end of options) is left alone
        (['--password', '--'], ['--password', '--'], None),
        # --password at end of args (used as flag) is left alone
        (['--password'], ['--password'], None),
        # -p at end of args (used as flag) is left alone
        (['-p'], ['-p'], None),
        # other args are preserved, only the password pair is extracted
        (['-u', 'root', '--password', '-mypass', '-h', 'localhost'], ['-u', 'root', '-h', 'localhost'], '-mypass'),
        (['-u', 'root', '-p-mypass', '-h', 'localhost'], ['-u', 'root', '-h', 'localhost'], '-mypass'),
        # -p as a flag does not absorb the next option
        (['-p', '-u', 'root'], ['-p', '-u', 'root'], None),
    ],
)
def test_normalize_password_args(args, expected_args, expected_password):
    assert _normalize_password_args(args) == expected_args
    assert cli_utils._extracted_password == expected_password
