"""Unit tests for mycli.config login path decryption."""
from io import BytesIO, TextIOWrapper
import os
import struct

from mycli.config import open_mylogin_cnf, read_and_decrypt_mylogin_cnf

LOGIN_PATH_FILE = os.path.abspath(os.path.join(os.path.dirname(__file__),
                                               'mylogin.cnf'))


def open_bmylogin_cnf(name):
    """Open contents of *name* in a BytesIO buffer."""
    with open(name, 'rb') as f:
        buf = BytesIO()
        buf.write(f.read())
    return buf


def test_read_mylogin_cnf():
    """Tests that a login path file can be read and decrypted."""
    mylogin_cnf = open_mylogin_cnf(LOGIN_PATH_FILE)

    assert isinstance(mylogin_cnf, TextIOWrapper)

    contents = mylogin_cnf.read()
    for word in ('[test]', 'user', 'password', 'host', 'port'):
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
    buf.write(b'\0\0\0\0\0\0\0\0\0\0')

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
    cipher_len, = struct.unpack("<i", len_buf)
    buf.read(cipher_len)

    # Corrupt the pad for the user line
    len_buf = buf.read(4)
    cipher_len, = struct.unpack("<i", len_buf)
    buf.read(cipher_len - 1)
    buf.write(b'\0')

    buf.seek(0)
    mylogin_cnf = TextIOWrapper(read_and_decrypt_mylogin_cnf(buf))
    contents = mylogin_cnf.read()
    for word in ('[test]', 'password', 'host', 'port'):
        assert word in contents
    assert 'user' not in contents
