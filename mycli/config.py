from __future__ import print_function
import shutil
from io import BytesIO, TextIOWrapper
import logging
import os
from os.path import exists
import struct
import sys
from configobj import ConfigObj, ConfigObjError
try:
    basestring
except NameError:
    basestring = str
try:
    from Crypto.Cipher import AES
except ImportError:
    AES = None


class CryptoError(Exception):
    """
    Exception to signal about pycrypto not available.
    """
    pass

logger = logging.getLogger(__name__)

def log(logger, level, message):
    """Logs message to stderr if logging isn't initialized."""

    if logger.parent.name != 'root':
        logger.log(level, message)
    else:
        print(message, file=sys.stderr)

def read_config_file(f):
    """Read a config file."""

    if isinstance(f, basestring):
        f = os.path.expanduser(f)

    try:
        config = ConfigObj(f, interpolation=False)
    except ConfigObjError as e:
        log(logger, logging.ERROR, "Unable to parse line {0} of config file "
            "'{1}'.".format(e.line_number, f))
        log(logger, logging.ERROR, "Using successfully parsed config values.")
        return e.config
    except (IOError, OSError) as e:
        log(logger, logging.WARNING, "You don't have permission to read "
            "config file '{0}'.".format(e.filename))
        return None

    return config

def read_config_files(files):
    """Read and merge a list of config files."""

    config = ConfigObj()

    for _file in files:
        _config = read_config_file(_file)
        if bool(_config) is True:
            config.merge(_config)
            config.filename = _config.filename

    return config

def write_default_config(source, destination, overwrite=False):
    destination = os.path.expanduser(destination)
    if not overwrite and exists(destination):
        return

    shutil.copyfile(source, destination)

def get_mylogin_cnf_path():
    """Return the path to the login path file or None if it doesn't exist."""
    mylogin_cnf_path = os.getenv('MYSQL_TEST_LOGIN_FILE')

    if mylogin_cnf_path is None:
        app_data = os.getenv('APPDATA')
        default_dir = os.path.join(app_data, 'MySQL') if app_data else '~'
        mylogin_cnf_path = os.path.join(default_dir, '.mylogin.cnf')

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
        with open(name, 'rb') as f:
            plaintext = read_and_decrypt_mylogin_cnf(f)
    except (OSError, IOError):
        logger.error('Unable to open login path file.')
        return None

    if not isinstance(plaintext, BytesIO):
        logger.error('Unable to read login path file.')
        return None

    return TextIOWrapper(plaintext)

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
    if AES is None:
        raise CryptoError('pycrypto is not available.')

    # Number of bytes used to store the length of ciphertext.
    MAX_CIPHER_STORE_LEN = 4

    LOGIN_KEY_LEN = 20

    # Move past the unused buffer.
    buf = f.read(4)

    if not buf or len(buf) != 4:
        logger.error('Login path file is blank or incomplete.')
        return None

    # Read the login key.
    key = f.read(LOGIN_KEY_LEN)

    # Generate the real key.
    rkey = [0] * 16
    for i in range(LOGIN_KEY_LEN):
        try:
            rkey[i % 16] ^= ord(key[i:i+1])
        except TypeError:
            # ord() was unable to get the value of the byte.
            logger.error('Unable to generate login path AES key.')
            return None
    rkey = struct.pack('16B', *rkey)

    # Create a cipher object using the key.
    aes_cipher = AES.new(rkey, AES.MODE_ECB)

    # Create a bytes buffer to hold the plaintext.
    plaintext = BytesIO()

    while True:
        # Read the length of the ciphertext.
        len_buf = f.read(MAX_CIPHER_STORE_LEN)
        if len(len_buf) < MAX_CIPHER_STORE_LEN:
            break
        cipher_len, = struct.unpack("<i", len_buf)

        # Read cipher_len bytes from the file and decrypt.
        cipher = f.read(cipher_len)
        pplain = aes_cipher.decrypt(cipher)

        try:
            # Determine pad length.
            pad_len = ord(pplain[-1:])
        except TypeError:
            # ord() was unable to get the value of the byte.
            logger.warning('Unable to remove pad.')
            continue

        if pad_len > len(pplain) or len(set(pplain[-pad_len:])) != 1:
            # Pad length should be less than or equal to the length of the
            # plaintext. The pad should have a single unqiue byte.
            logger.warning('Invalid pad found in login path file.')
            continue

        # Get rid of pad.
        plain = pplain[:-pad_len]
        plaintext.write(plain)

    if plaintext.tell() == 0:
        logger.error('No data successfully decrypted from login path file.')
        return None

    plaintext.seek(0)
    return plaintext

def str_to_bool(s):
    """Convert a string value to its corresponding boolean value."""
    if isinstance(s, bool):
        return s
    elif not isinstance(s, basestring):
        raise TypeError('argument must be a string')

    true_values = ('true', 'on', '1')
    false_values = ('false', 'off', '0')

    if s.lower() in true_values:
        return True
    elif s.lower() in false_values:
        return False
    else:
        raise ValueError('not a recognized boolean value: %s'.format(s))
