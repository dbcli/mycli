# -*- coding: utf-8 -*-
"""Platform and Python version compatibility support."""

import sys


PY2 = sys.version_info[0] == 2
PY3 = sys.version_info[0] == 3
WIN = sys.platform in ('win32', 'cygwin')
