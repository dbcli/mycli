import binascii
import sys

PY2 = sys.version_info[0] == 2
PY3 = sys.version_info[0] == 3


def unicode2utf8(arg):
    """
    Only in Python 2. Psycopg2 expects the args as bytes not unicode.
    In Python 3 the args are expected as unicode.
    """

    if PY2 and isinstance(arg, unicode):
        return arg.encode('utf-8')
    return arg


def utf8tounicode(arg):
    """
    Only in Python 2. Psycopg2 returns the error message as utf-8.
    In Python 3 the errors are returned as unicode.
    """

    if PY2 and isinstance(arg, str):
        return arg.decode('utf-8')
    return arg


def bytes_to_hex(b):
    """Convert bytes that cannot be decoded to utf8 to hexlified string.

    >>> print(bytes_to_hex(b"\\xff"))
    0xff
    >>> print(bytes_to_hex('abc'))
    abc
    >>> print(bytes_to_hex('✌'))
    ✌
    """
    if isinstance(b, bytes):
        try:
            b.decode('utf8')
        except:
            b = '0x' + binascii.hexlify(b).decode('ascii')
    return b
