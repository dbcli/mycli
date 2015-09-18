import shutil
from io import BytesIO, TextIOWrapper
import logging
import os
from os.path import expanduser, exists
import struct
from configobj import ConfigObj
from Crypto.Cipher import AES

logger = logging.getLogger(__name__)

def load_config(usr_cfg, def_cfg=None):
    cfg = ConfigObj()
    cfg.merge(ConfigObj(def_cfg, interpolation=False))
    cfg.merge(ConfigObj(expanduser(usr_cfg), interpolation=False))
    cfg.filename = expanduser(usr_cfg)

    return cfg

def write_default_config(source, destination, overwrite=False):
    destination = expanduser(destination)
    if not overwrite and exists(destination):
        return

    shutil.copyfile(source, destination)

def get_mylogin_cnf_path():
    """Return the path to the .mylogin.cnf file or None if doesn't exist."""
    app_data = os.getenv('APPDATA')
    if app_data is None:
        mylogin_config_dir = os.path.expanduser('~')
    else:
        mylogin_config_dir = os.path.join(app_data, 'MySQL')

    mylogin_config_dir = os.path.abspath(mylogin_config_dir)
    mylogin_config_path = os.path.join(mylogin_config_dir, '.mylogin.cnf')

    return mylogin_config_path if exists(mylogin_config_path) else None

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
        logger.error("Error: Unable to open '{0}'".format(name))
        return None

    if not isinstance(plaintext, BytesIO):
        logger.error("Error: Unable to decrypt '{0}'".format(name))
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
    :rtype: io.BytesIO
    """

    # Number of bytes used to store the length of ciphertext.
    MAX_CIPHER_STORE_LEN = 4

    LOGIN_KEY_LEN = 20

    # Move past the unused buffer.
    f.seek(4)

    # Read the login key.
    key = f.read(LOGIN_KEY_LEN)

    # Generate the real key.
    rkey = [0] * 16
    for i in range(LOGIN_KEY_LEN):
        rkey[i % 16] ^= ord(key[i:i+1])
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
        plain = aes_cipher.decrypt(cipher)

        # Get rid of pad
        plain = plain[:-ord(plain[-1:])]
        plaintext.write(plain)

    plaintext.seek(0)
    return plaintext
