# type: ignore

import pytest

from mycli.packages.cli_utils import (
    is_valid_connection_scheme,
)


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
