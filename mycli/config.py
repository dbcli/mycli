from copy import copy
from importlib import resources
from io import BytesIO, TextIOWrapper
import logging
import os
from os.path import exists
import struct
import sys
from typing import IO, Union

from configobj import ConfigObj, ConfigObjError
import pyaes

logger = logging.getLogger(__name__)


def log(logger, level, message):
    """Logs message to stderr if logging isn't initialized."""

    if logger.parent.name != "root":
        logger.log(level, message)
    else:
        print(message, file=sys.stderr)


def read_config_file(f, list_values=True):
    """Read a config file.

    *list_values* set to `True` is the default behavior of ConfigObj.
    Disabling it causes values to not be parsed for lists,
    (e.g. 'a,b,c' -> ['a', 'b', 'c']. Additionally, the config values are
    not unquoted. We are disabling list_values when reading MySQL config files
    so we can correctly interpret commas in passwords.

    """

    if isinstance(f, str):
        f = os.path.expanduser(f)

    try:
        config = ConfigObj(f, interpolation=False, encoding="utf8", list_values=list_values)
    except ConfigObjError as e:
        log(logger, logging.WARNING, "Unable to parse line {0} of config file '{1}'.".format(e.line_number, f))
        log(logger, logging.WARNING, "Using successfully parsed config values.")
        return e.config
    except (IOError, OSError) as e:
        log(logger, logging.WARNING, "You don't have permission to read config file '{0}'.".format(e.filename))
        return None

    return config


def get_included_configs(config_file: Union[str, TextIOWrapper]) -> list:
    """Get a list of configuration files that are included into config_path
    with !includedir directive.

    "Normal" configs should be passed as file paths. The only exception
    is .mylogin which is decoded into a stream. However, it never
    contains include directives and so will be ignored by this
    function.

    """
    if not isinstance(config_file, str) or not os.path.isfile(config_file):
        return []
    included_configs = []

    try:
        with open(config_file) as f:
            include_directives = filter(lambda s: s.startswith("!includedir"), f)
            dirs_split = (s.strip().split()[-1] for s in include_directives)
            dirs = filter(os.path.isdir, dirs_split)
            for dir_ in dirs:
                for filename in os.listdir(dir_):
                    if filename.endswith(".cnf"):
                        included_configs.append(os.path.join(dir_, filename))
    except (PermissionError, UnicodeDecodeError):
        pass
    return included_configs


def read_config_files(files, list_values=True):
    """Read and merge a list of config files."""

    config = create_default_config(list_values=list_values)
    _files = copy(files)
    while _files:
        _file = _files.pop(0)
        _config = read_config_file(_file, list_values=list_values)

        # expand includes only if we were able to parse config
        # (otherwise we'll just encounter the same errors again)
        if config is not None:
            _files = get_included_configs(_file) + _files
        if bool(_config) is True:
            config.merge(_config)
            config.filename = _config.filename

    return config


def create_default_config(list_values=True):
    import mycli

    default_config_file = resources.open_text(mycli, "myclirc")
    return read_config_file(default_config_file, list_values=list_values)


def write_default_config(destination, overwrite=False):
    import mycli

    default_config = resources.read_text(mycli, "myclirc")
    destination = os.path.expanduser(destination)
    if not overwrite and exists(destination):
        return

    with open(destination, "w") as f:
        f.write(default_config)


def get_mylogin_cnf_path():
    """Return the path to the login path file or None if it doesn't exist."""
    mylogin_cnf_path = os.getenv("MYSQL_TEST_LOGIN_FILE")

    if mylogin_cnf_path is None:
        app_data = os.getenv("APPDATA")
        default_dir = os.path.join(app_data, "MySQL") if app_data else "~"
        mylogin_cnf_path = os.path.join(default_dir, ".mylogin.cnf")

    mylogin_cnf_path = os.path.expanduser(mylogin_cnf_path)

    if exists(mylogin_cnf_path):
        logger.debug("Found login path file at '{0}'".format(mylogin_cnf_path))
        return mylogin_cnf_path
    return None


def open_mylogin_cnf(name):
    """Open a readable version of .mylogin.cnf.

    Returns the file contents as a TextIOWrapper object.

    :param str name: The pathname of the file to be opened.
    :return: the login path file or None
    """

    try:
        with open(name, "rb") as f:
            plaintext = read_and_decrypt_mylogin_cnf(f)
    except (OSError, IOError, ValueError):
        logger.error("Unable to open login path file.")
        return None

    if not isinstance(plaintext, BytesIO):
        logger.error("Unable to read login path file.")
        return None

    return TextIOWrapper(plaintext)


# TODO reuse code between encryption an decryption
def encrypt_mylogin_cnf(plaintext: IO[str]):
    """Encryption of .mylogin.cnf file, analogous to calling
    mysql_config_editor.

    Code is based on the python implementation by Kristian Koehntopp
    https://github.com/isotopp/mysql-config-coder

    """

    def realkey(key):
        """Create the AES key from the login key."""
        rkey = bytearray(16)
        for i in range(len(key)):
            rkey[i % 16] ^= key[i]
        return bytes(rkey)

    def encode_line(plaintext, real_key, buf_len):
        aes = pyaes.AESModeOfOperationECB(real_key)
        text_len = len(plaintext)
        pad_len = buf_len - text_len
        pad_chr = bytes(chr(pad_len), "utf8")
        plaintext = plaintext.encode() + pad_chr * pad_len
        encrypted_text = b"".join([aes.encrypt(plaintext[i : i + 16]) for i in range(0, len(plaintext), 16)])
        return encrypted_text

    LOGIN_KEY_LENGTH = 20
    key = os.urandom(LOGIN_KEY_LENGTH)
    real_key = realkey(key)

    outfile = BytesIO()

    outfile.write(struct.pack("i", 0))
    outfile.write(key)

    while True:
        line = plaintext.readline()
        if not line:
            break
        real_len = len(line)
        pad_len = (int(real_len / 16) + 1) * 16

        outfile.write(struct.pack("i", pad_len))
        x = encode_line(line, real_key, pad_len)
        outfile.write(x)

    outfile.seek(0)
    return outfile


def read_and_decrypt_mylogin_cnf(f):
    """Read and decrypt the contents of .mylogin.cnf.

    This decryption algorithm mimics the code in MySQL's
    mysql_config_editor.cc.

    The login key is 20-bytes of random non-printable ASCII.
    It is written to the actual login path file. It is used
    to generate the real key used in the AES cipher.

    :param f: an I/O object opened in binary mode
    :return: the decrypted login path file
    :rtype: io.BytesIO or None
    """

    # Number of bytes used to store the length of ciphertext.
    MAX_CIPHER_STORE_LEN = 4

    LOGIN_KEY_LEN = 20

    # Move past the unused buffer.
    buf = f.read(4)

    if not buf or len(buf) != 4:
        logger.error("Login path file is blank or incomplete.")
        return None

    # Read the login key.
    key = f.read(LOGIN_KEY_LEN)

    # Generate the real key.
    rkey = [0] * 16
    for i in range(LOGIN_KEY_LEN):
        try:
            rkey[i % 16] ^= ord(key[i : i + 1])
        except TypeError:
            # ord() was unable to get the value of the byte.
            logger.error("Unable to generate login path AES key.")
            return None
    rkey = struct.pack("16B", *rkey)

    # Create a bytes buffer to hold the plaintext.
    plaintext = BytesIO()
    aes = pyaes.AESModeOfOperationECB(rkey)

    while True:
        # Read the length of the ciphertext.
        len_buf = f.read(MAX_CIPHER_STORE_LEN)
        if len(len_buf) < MAX_CIPHER_STORE_LEN:
            break
        (cipher_len,) = struct.unpack("<i", len_buf)

        # Read cipher_len bytes from the file and decrypt.
        cipher = f.read(cipher_len)
        plain = _remove_pad(b"".join([aes.decrypt(cipher[i : i + 16]) for i in range(0, cipher_len, 16)]))
        if plain is False:
            continue
        plaintext.write(plain)

    if plaintext.tell() == 0:
        logger.error("No data successfully decrypted from login path file.")
        return None

    plaintext.seek(0)
    return plaintext


def str_to_bool(s):
    """Convert a string value to its corresponding boolean value."""
    if isinstance(s, bool):
        return s
    elif not isinstance(s, str):
        raise TypeError("argument must be a string")

    true_values = ("true", "on", "1")
    false_values = ("false", "off", "0")

    if s.lower() in true_values:
        return True
    elif s.lower() in false_values:
        return False
    else:
        raise ValueError("not a recognized boolean value: {0}".format(s))


def strip_matching_quotes(s):
    """Remove matching, surrounding quotes from a string.

    This is the same logic that ConfigObj uses when parsing config
    values.

    """
    if isinstance(s, str) and len(s) >= 2 and s[0] == s[-1] and s[0] in ('"', "'"):
        s = s[1:-1]
    return s


def _remove_pad(line):
    """Remove the pad from the *line*."""
    try:
        # Determine pad length.
        pad_length = ord(line[-1:])
    except TypeError:
        # ord() was unable to get the value of the byte.
        logger.warning("Unable to remove pad.")
        return False

    if pad_length > len(line) or len(set(line[-pad_length:])) != 1:
        # Pad length should be less than or equal to the length of the
        # plaintext. The pad should have a single unique byte.
        logger.warning("Invalid pad found in login path file.")
        return False

    return line[:-pad_length]
