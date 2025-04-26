"""Unit tests for the mycli.config module."""

from io import BytesIO, StringIO, TextIOWrapper
import os
import struct
import sys
import tempfile

import pytest

from mycli.config import (
    get_mylogin_cnf_path,
    open_mylogin_cnf,
    read_and_decrypt_mylogin_cnf,
    read_config_file,
    str_to_bool,
    strip_matching_quotes,
)

LOGIN_PATH_FILE = os.path.abspath(os.path.join(os.path.dirname(__file__), "mylogin.cnf"))


def open_bmylogin_cnf(name):
    """Open contents of *name* in a BytesIO buffer."""
    with open(name, "rb") as f:
        buf = BytesIO()
        buf.write(f.read())
    return buf


def test_read_mylogin_cnf():
    """Tests that a login path file can be read and decrypted."""
    mylogin_cnf = open_mylogin_cnf(LOGIN_PATH_FILE)

    assert isinstance(mylogin_cnf, TextIOWrapper)

    contents = mylogin_cnf.read()
    for word in ("[test]", "user", "password", "host", "port"):
        assert word in contents


def test_decrypt_blank_mylogin_cnf():
    """Test that a blank login path file is handled correctly."""
    mylogin_cnf = read_and_decrypt_mylogin_cnf(BytesIO())
    assert mylogin_cnf is None


def test_corrupted_login_key():
    """Test that a corrupted login path key is handled correctly."""
    buf = open_bmylogin_cnf(LOGIN_PATH_FILE)

    # Skip past the unused bytes
    buf.seek(4)

    # Write null bytes over half the login key
    buf.write(b"\0\0\0\0\0\0\0\0\0\0")

    buf.seek(0)
    mylogin_cnf = read_and_decrypt_mylogin_cnf(buf)

    assert mylogin_cnf is None


def test_corrupted_pad():
    """Tests that a login path file with a corrupted pad is partially read."""
    buf = open_bmylogin_cnf(LOGIN_PATH_FILE)

    # Skip past the login key
    buf.seek(24)

    # Skip option group
    len_buf = buf.read(4)
    (cipher_len,) = struct.unpack("<i", len_buf)
    buf.read(cipher_len)

    # Corrupt the pad for the user line
    len_buf = buf.read(4)
    (cipher_len,) = struct.unpack("<i", len_buf)
    buf.read(cipher_len - 1)
    buf.write(b"\0")

    buf.seek(0)
    mylogin_cnf = TextIOWrapper(read_and_decrypt_mylogin_cnf(buf))
    contents = mylogin_cnf.read()
    for word in ("[test]", "password", "host", "port"):
        assert word in contents
    assert "user" not in contents


def test_get_mylogin_cnf_path():
    """Tests that the path for .mylogin.cnf is detected."""
    original_env = None
    if "MYSQL_TEST_LOGIN_FILE" in os.environ:
        original_env = os.environ.pop("MYSQL_TEST_LOGIN_FILE")
    is_windows = sys.platform == "win32"

    login_cnf_path = get_mylogin_cnf_path()

    if original_env is not None:
        os.environ["MYSQL_TEST_LOGIN_FILE"] = original_env

    if login_cnf_path is not None:
        assert login_cnf_path.endswith(".mylogin.cnf")

        if is_windows is True:
            assert "MySQL" in login_cnf_path
        else:
            home_dir = os.path.expanduser("~")
            assert login_cnf_path.startswith(home_dir)


def test_alternate_get_mylogin_cnf_path():
    """Tests that the alternate path for .mylogin.cnf is detected."""
    original_env = None
    if "MYSQL_TEST_LOGIN_FILE" in os.environ:
        original_env = os.environ.pop("MYSQL_TEST_LOGIN_FILE")

    _, temp_path = tempfile.mkstemp()
    os.environ["MYSQL_TEST_LOGIN_FILE"] = temp_path

    login_cnf_path = get_mylogin_cnf_path()

    if original_env is not None:
        os.environ["MYSQL_TEST_LOGIN_FILE"] = original_env

    assert temp_path == login_cnf_path


def test_str_to_bool():
    """Tests that str_to_bool function converts values correctly."""

    assert str_to_bool(False) is False
    assert str_to_bool(True) is True
    assert str_to_bool("False") is False
    assert str_to_bool("True") is True
    assert str_to_bool("TRUE") is True
    assert str_to_bool("1") is True
    assert str_to_bool("0") is False
    assert str_to_bool("on") is True
    assert str_to_bool("off") is False
    assert str_to_bool("off") is False

    with pytest.raises(ValueError):
        str_to_bool("foo")

    with pytest.raises(TypeError):
        str_to_bool(None)


def test_read_config_file_list_values_default():
    """Test that reading a config file uses list_values by default."""

    f = StringIO("[main]\nweather='cloudy with a chance of meatballs'\n")
    config = read_config_file(f)

    assert config["main"]["weather"] == "cloudy with a chance of meatballs"


def test_read_config_file_list_values_off():
    """Test that you can disable list_values when reading a config file."""

    f = StringIO("[main]\nweather='cloudy with a chance of meatballs'\n")
    config = read_config_file(f, list_values=False)

    assert config["main"]["weather"] == "'cloudy with a chance of meatballs'"


def test_strip_quotes_with_matching_quotes():
    """Test that a string with matching quotes is unquoted."""

    s = "May the force be with you."
    assert s == strip_matching_quotes('"{}"'.format(s))
    assert s == strip_matching_quotes("'{}'".format(s))


def test_strip_quotes_with_unmatching_quotes():
    """Test that a string with unmatching quotes is not unquoted."""

    s = "May the force be with you."
    assert '"' + s == strip_matching_quotes('"{}'.format(s))
    assert s + "'" == strip_matching_quotes("{}'".format(s))


def test_strip_quotes_with_empty_string():
    """Test that an empty string is handled during unquoting."""

    assert "" == strip_matching_quotes("")


def test_strip_quotes_with_none():
    """Test that None is handled during unquoting."""

    assert None is strip_matching_quotes(None)


def test_strip_quotes_with_quotes():
    """Test that strings with quotes in them are handled during unquoting."""

    s1 = 'Darth Vader said, "Luke, I am your father."'
    assert s1 == strip_matching_quotes(s1)

    s2 = '"Darth Vader said, "Luke, I am your father.""'
    assert s2[1:-1] == strip_matching_quotes(s2)
