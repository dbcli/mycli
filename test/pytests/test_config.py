# type: ignore

"""Unit tests for the mycli.config module."""

import builtins
from io import BytesIO, StringIO, TextIOWrapper
import logging
import os
import struct
import sys
from tempfile import NamedTemporaryFile
from types import SimpleNamespace

from configobj import ConfigObj
import pytest

from mycli import config as config_module
from mycli.config import (
    _remove_pad,
    create_default_config,
    encrypt_mylogin_cnf,
    get_included_configs,
    get_mylogin_cnf_path,
    log,
    open_mylogin_cnf,
    read_and_decrypt_mylogin_cnf,
    read_config_file,
    read_config_files,
    str_to_bool,
    strip_matching_quotes,
    write_default_config,
)
from test.utils import TEMPFILE_PREFIX

LOGIN_PATH_FILE = os.path.abspath(os.path.join(os.path.dirname(__file__), "../mylogin.cnf"))


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


def test_get_mylogin_cnf_path(monkeypatch):
    """Tests that the path for .mylogin.cnf is detected."""
    monkeypatch.delenv('MYSQL_TEST_LOGIN_FILE', raising=False)
    is_windows = sys.platform == "win32"

    login_cnf_path = get_mylogin_cnf_path()

    if login_cnf_path is not None:
        assert login_cnf_path.endswith(".mylogin.cnf")

        if is_windows is True:
            assert "MySQL" in login_cnf_path
        else:
            home_dir = os.path.expanduser("~")
            assert login_cnf_path.startswith(home_dir)


def test_alternate_get_mylogin_cnf_path(monkeypatch):
    """Tests that the alternate path for .mylogin.cnf is detected."""

    with NamedTemporaryFile(prefix=TEMPFILE_PREFIX, mode='w', delete=False) as login_file:
        monkeypatch.setenv('MYSQL_TEST_LOGIN_FILE', login_file.name)
        login_cnf_path = get_mylogin_cnf_path()

    try:
        assert login_file.name == login_cnf_path
    except AssertionError as e:
        assert AssertionError(e)
    finally:
        if os.path.exists(login_file.name):
            os.remove(login_file.name)


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


def test_log_prints_to_stderr_when_root_logger(capsys) -> None:
    fake_logger = SimpleNamespace(parent=SimpleNamespace(name='root'), log=lambda level, message: None)

    log(fake_logger, logging.WARNING, 'root warning')

    assert capsys.readouterr().err == 'root warning\n'


def test_read_config_file_from_path_and_parse_error(tmp_path, capsys) -> None:
    valid_path = tmp_path / 'valid.cnf'
    valid_path.write_text('[main]\ncolor = blue\n', encoding='utf8')

    config = read_config_file(str(valid_path))
    assert config['main']['color'] == 'blue'

    invalid_path = tmp_path / 'invalid.cnf'
    invalid_path.write_text('[main\nfoo=bar\n', encoding='utf8')

    parsed = read_config_file(str(invalid_path))
    assert parsed['foo'] == 'bar'

    stderr = capsys.readouterr().err
    assert "Unable to parse line 1 of config file" in stderr
    assert 'Using successfully parsed config values.' in stderr


def test_read_config_file_permission_error(monkeypatch, capsys) -> None:
    def raise_oserror(*_args, **_kwargs):
        raise OSError(13, 'denied', '/tmp/test.cnf')

    monkeypatch.setattr(config_module, 'ConfigObj', raise_oserror)

    assert read_config_file('/tmp/test.cnf') is None
    assert "You don't have permission to read config file '/tmp/test.cnf'." in capsys.readouterr().err


def test_get_included_configs_handles_paths_and_errors(tmp_path, monkeypatch) -> None:
    include_dir = tmp_path / 'includes'
    include_dir.mkdir()
    expected = include_dir / 'included.cnf'
    expected.write_text('[main]\nfoo = bar\n', encoding='utf8')
    (include_dir / 'ignore.txt').write_text('skip', encoding='utf8')

    config_path = tmp_path / 'root.cnf'
    config_path.write_text(f'!includedir {include_dir}\n', encoding='utf8')

    assert get_included_configs(BytesIO()) == []
    assert get_included_configs(str(tmp_path / 'missing.cnf')) == []
    assert get_included_configs(str(config_path)) == [str(expected)]

    monkeypatch.setattr(builtins, 'open', lambda *_args, **_kwargs: (_ for _ in ()).throw(PermissionError()))
    assert get_included_configs(str(config_path)) == []


def test_read_config_files_merges_includes_and_honors_flags(monkeypatch) -> None:
    first_config = ConfigObj({'main': {'color': 'blue'}})
    first_config.filename = 'first.cnf'
    included_config = ConfigObj({'main': {'pager': 'less'}})
    included_config.filename = 'included.cnf'

    monkeypatch.setattr(config_module, 'create_default_config', lambda list_values=True: ConfigObj({'default': {'a': '1'}}))

    def fake_read_config_file(filename, list_values=True):
        if filename == 'first.cnf':
            return first_config
        if filename == 'included.cnf':
            return included_config
        return None

    monkeypatch.setattr(config_module, 'read_config_file', fake_read_config_file)
    monkeypatch.setattr(config_module, 'get_included_configs', lambda filename: ['included.cnf'] if filename == 'first.cnf' else [])

    merged = read_config_files(['first.cnf'])
    assert merged['default']['a'] == '1'
    assert merged['main']['color'] == 'blue'
    assert merged['main']['pager'] == 'less'
    assert merged.filename == 'included.cnf'

    ignored_defaults = read_config_files(['first.cnf'], ignore_package_defaults=True)
    assert 'default' not in ignored_defaults
    assert ignored_defaults['main']['color'] == 'blue'

    untouched = read_config_files(['first.cnf'], ignore_user_options=True)
    assert untouched == ConfigObj({'default': {'a': '1'}})
    assert 'main' not in untouched


def test_create_and_write_default_config(tmp_path) -> None:
    default_config = create_default_config()
    assert 'main' in default_config

    destination = tmp_path / 'myclirc'
    write_default_config(str(destination))
    written = destination.read_text(encoding='utf8')
    assert '[main]' in written

    destination.write_text('custom', encoding='utf8')
    write_default_config(str(destination))
    assert destination.read_text(encoding='utf8') == 'custom'

    write_default_config(str(destination), overwrite=True)
    assert '[main]' in destination.read_text(encoding='utf8')


def test_get_mylogin_cnf_path_returns_none_for_missing_file(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv('MYSQL_TEST_LOGIN_FILE', str(tmp_path / 'missing.mylogin.cnf'))

    assert get_mylogin_cnf_path() is None


def test_open_mylogin_cnf_error_paths(monkeypatch, tmp_path, caplog) -> None:
    with caplog.at_level(logging.ERROR):
        assert open_mylogin_cnf(str(tmp_path / 'missing.mylogin.cnf')) is None
    assert 'Unable to open login path file.' in caplog.text

    caplog.clear()
    existing = tmp_path / 'present.mylogin.cnf'
    existing.write_bytes(b'not-used')
    monkeypatch.setattr(config_module, 'read_and_decrypt_mylogin_cnf', lambda f: None)

    with caplog.at_level(logging.ERROR):
        assert open_mylogin_cnf(str(existing)) is None
    assert 'Unable to read login path file.' in caplog.text


def test_encrypt_mylogin_cnf_round_trip() -> None:
    plaintext = StringIO('[client]\nuser=test\npassword=secret\n')

    encrypted = encrypt_mylogin_cnf(plaintext)
    decrypted = read_and_decrypt_mylogin_cnf(encrypted)

    assert isinstance(encrypted, BytesIO)
    assert decrypted.read().decode('utf8') == '[client]\nuser=test\npassword=secret\n'


def test_read_and_decrypt_mylogin_cnf_error_branches(caplog) -> None:
    incomplete_key = BytesIO(struct.pack('i', 0) + b'a')
    with caplog.at_level(logging.ERROR):
        assert read_and_decrypt_mylogin_cnf(incomplete_key) is None
    assert 'Unable to generate login path AES key.' in caplog.text

    caplog.clear()
    no_payload = BytesIO(struct.pack('i', 0) + b'0123456789abcdefghij')
    with caplog.at_level(logging.ERROR):
        assert read_and_decrypt_mylogin_cnf(no_payload) is None
    assert 'No data successfully decrypted from login path file.' in caplog.text


def test_remove_pad_valid_and_invalid_cases(caplog) -> None:
    assert _remove_pad(b'hello\x03\x03\x03') == b'hello'

    with caplog.at_level(logging.WARNING):
        assert _remove_pad(b'') is False
    assert 'Unable to remove pad.' in caplog.text

    caplog.clear()
    with caplog.at_level(logging.WARNING):
        assert _remove_pad(b'hello\x02\x03') is False
    assert 'Invalid pad found in login path file.' in caplog.text


def test_strip_quotes_with_matching_quotes():
    """Test that a string with matching quotes is unquoted."""

    s = "May the force be with you."
    assert s == strip_matching_quotes(f'"{s}"')
    assert s == strip_matching_quotes(f"'{s}'")


def test_strip_quotes_with_unmatching_quotes():
    """Test that a string with unmatching quotes is not unquoted."""

    s = "May the force be with you."
    assert '"' + s == strip_matching_quotes(f'"{s}')
    assert s + "'" == strip_matching_quotes(f"{s}'")


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
