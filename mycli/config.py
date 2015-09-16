import shutil
from io import BytesIO, TextIOWrapper
import os
from os.path import expanduser, exists
import struct
from configobj import ConfigObj
from Crypto.Cipher import AES

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

def get_mylogin_cnf_plaintext(file_name):
    """Return the contents of .mylogin.cnf as a buffered text stream."""

    # Number of bytes used to store the length of ciphertext.
    MAX_CIPHER_STORE_LEN = 4
    LOGIN_KEY_LEN = 20

    with open(file_name, 'rb') as f:
        # Move past the unused buffer.
        f.seek(4)

        # Read the login key, a sequence of random non-printable ASCII.
        key = f.read(LOGIN_KEY_LEN)

        # Generate the real AES key
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
        return TextIOWrapper(plaintext)
