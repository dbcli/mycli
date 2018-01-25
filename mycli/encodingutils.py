# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from mycli.compat import PY2


if PY2:
    text_type = unicode
    binary_type = str
else:
    text_type = str
    binary_type = bytes


def unicode2utf8(arg):
    """Convert strings to UTF8-encoded bytes.

    Only in Python 2. In Python 3 the args are expected as unicode.

    """

    if PY2 and isinstance(arg, text_type):
        return arg.encode('utf-8')
    return arg


def utf8tounicode(arg):
    """Convert UTF8-encoded bytes to strings.

    Only in Python 2. In Python 3 the errors are returned as strings.

    """

    if PY2 and isinstance(arg, binary_type):
        return arg.decode('utf-8')
    return arg
